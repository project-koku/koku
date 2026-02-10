#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP data validation and sanitization utilities.

This module provides validation and sanitization functions for data ingested
from the Cost Management Metrics Operator to prevent security issues like
SQL injection and XSS attacks.

Usage:
    # Import to register the accessor
    import masu.util.ocp.ocp_data_validator  # noqa: F401

    # Then use directly on any DataFrame:
    df, issues = df.ocp.validate_and_sanitize()

    # Or individual operations:
    df, issues = df.ocp.validate()
    df = df.ocp.sanitize()

    # Check for malicious content:
    if df.ocp.has_malicious_content():
        raise SecurityError("Malicious content detected")
"""
import html
import re

import pandas as pd


class OCPDataValidationError(Exception):
    """Exception raised when OCP data validation fails."""

    def __init__(self, message: str, field: str = None, value: str = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)


@pd.api.extensions.register_dataframe_accessor("ocp")
class OCPDataFrameAccessor:
    """Pandas DataFrame accessor for OCP data validation and sanitization."""

    # Fields to validate and sanitize - user-controllable string fields from OCP data
    FIELDS_TO_VALIDATE = (
        "namespace",
        "pod",
        "node",
        "persistentvolumeclaim",
        "persistentvolume",
        "storageclass",
        "resource_id",
        "vm_name",
        "gpu_uuid",
        "gpu_model_name",
        "gpu_vendor_name",
        "csi_driver",
        "csi_volume_handle",
        "node_role",
        "vm_instance_type",
        "vm_os",
        "vm_device",
    )

    # Maximum length constraints for OCP fields
    # Based on Kubernetes resource naming constraints and practical limits
    FIELD_MAX_LENGTHS = {
        "namespace": 253,
        "pod": 253,
        "node": 253,
        "persistentvolumeclaim": 253,
        "persistentvolume": 253,
        "storageclass": 253,
        "resource_id": 512,
        "cluster_id": 253,
        "vm_name": 253,
        "gpu_uuid": 128,
        "gpu_model_name": 256,
        "gpu_vendor_name": 128,
        "csi_driver": 253,
        "csi_volume_handle": 512,
        "node_role": 128,
        "vm_instance_type": 128,
        "vm_os": 128,
        "vm_guest_os_arch": 64,
        "vm_guest_os_name": 128,
        "vm_guest_os_version": 64,
        "vm_device": 253,
        "vm_volume_mode": 64,
        "vm_persistentvolumeclaim_name": 253,
    }

    # Combined pattern for SQL injection and XSS detection (vectorized matching)
    _MALICIOUS_PATTERN = re.compile(
        # SQL injection patterns
        r"('|\")\s*(OR|AND|UNION|SELECT|INSERT|UPDATE|DELETE|DROP|;|--)"
        r"|UNION\s+(ALL\s+)?SELECT"
        r"|SELECT\s+.+\s+FROM"
        r"|INSERT\s+INTO"
        r"|UPDATE\s+.+\s+SET"
        r"|DELETE\s+FROM"
        r"|DROP\s+(TABLE|DATABASE|INDEX)"
        r"|;\s*(SELECT|INSERT|UPDATE|DELETE|DROP)"
        r"|--\s*$|#\s*$"
        r"|/\*.*\*/"
        # XSS patterns
        r"|<script[^>]*>"
        r"|</script>"
        r"|javascript:"
        r"|on\w+\s*="
        r"|<iframe[^>]*>"
        r"|<object[^>]*>"
        r"|<embed[^>]*>"
        r"|<svg[^>]*onload"
        r"|data:\s*text/html"
        r"|expression\s*\(",
        re.IGNORECASE,
    )

    def __init__(self, pandas_obj: pd.DataFrame):
        self._obj = pandas_obj

    def _get_string_series(self, field: str) -> tuple[pd.Series, pd.Series]:
        """Get a series of string values and a mask for the field.

        Returns:
            Tuple of (string_series, string_mask) where string_series contains
            only non-null string values and string_mask indicates which rows
            have string values.
        """
        col = self._obj[field]
        # Use object dtype check - strings in pandas are typically object dtype
        str_mask = col.notna()
        if str_mask.any():
            # Filter to actual strings (handles mixed-type columns)
            str_mask = str_mask & col.apply(lambda x: isinstance(x, str))
        return col[str_mask], str_mask

    def validate(self) -> tuple[pd.DataFrame, list[str]]:
        """
        Validate the DataFrame for malicious content and constraint violations.

        Uses vectorized operations for efficiency with large DataFrames.

        Returns:
            A tuple of (dataframe, list_of_issues).
        """
        issues = []

        for field in self.FIELDS_TO_VALIDATE:
            if field not in self._obj.columns:
                continue

            str_series, _ = self._get_string_series(field)

            if str_series.empty:
                continue

            # Vectorized regex check for malicious content
            malicious_mask = str_series.str.contains(self._MALICIOUS_PATTERN, regex=True, na=False)

            if malicious_mask.any():
                bad_values = str_series[malicious_mask].unique()
                for val in bad_values:
                    truncated = val[:50] + "..." if len(val) > 50 else val
                    issues.append(f"Potentially malicious content in field '{field}': {truncated}")

            # Vectorized length check
            if max_length := self.FIELD_MAX_LENGTHS.get(field):
                too_long_mask = str_series.str.len() > max_length
                if too_long_mask.any():
                    count = too_long_mask.sum()
                    issues.append(f"Field '{field}' has {count} value(s) exceeding max length {max_length}")

        return self._obj, issues

    def sanitize(self) -> pd.DataFrame:
        """
        Sanitize string columns in the DataFrame.

        Uses vectorized operations where possible for efficiency.

        Returns:
            The sanitized DataFrame.
        """
        for field in self.FIELDS_TO_VALIDATE:
            if field not in self._obj.columns:
                continue

            _, str_mask = self._get_string_series(field)

            if not str_mask.any():
                continue

            # Vectorized null byte removal
            self._obj.loc[str_mask, field] = self._obj.loc[str_mask, field].str.replace("\x00", "", regex=False)

            # HTML escape (requires apply - no vectorized version available)
            self._obj.loc[str_mask, field] = self._obj.loc[str_mask, field].apply(lambda x: html.escape(x, quote=True))

        return self._obj

    def validate_and_sanitize(self, strict: bool = False) -> tuple[pd.DataFrame, list[str]]:
        """
        Validate and sanitize the DataFrame.

        Args:
            strict: If True, raise exception on validation errors.

        Returns:
            A tuple of (processed_dataframe, list_of_issues).

        Raises:
            OCPDataValidationError: If strict=True and validation fails.
        """
        _, issues = self.validate()

        if strict and issues:
            raise OCPDataValidationError(
                f"Data validation failed with {len(issues)} issues: {issues[0]}",
                field="multiple",
            )

        self.sanitize()
        return self._obj, issues

    def has_malicious_content(self) -> bool:
        """
        Check if the DataFrame contains any potentially malicious content.

        Uses vectorized operations for efficiency.

        Returns:
            True if malicious content is detected in any field.
        """
        for field in self.FIELDS_TO_VALIDATE:
            if field not in self._obj.columns:
                continue

            str_series, _ = self._get_string_series(field)

            if str_series.empty:
                continue

            # Vectorized check - returns True immediately if any match found
            if str_series.str.contains(self._MALICIOUS_PATTERN, regex=True, na=False).any():
                return True

        return False

    def get_malicious_fields(self) -> dict[str, list[str]]:
        """
        Get a dictionary of fields containing malicious content.

        Returns:
            Dict mapping field names to lists of malicious values found.
        """
        malicious = {}

        for field in self.FIELDS_TO_VALIDATE:
            if field not in self._obj.columns:
                continue

            str_series, _ = self._get_string_series(field)

            if str_series.empty:
                continue

            # Vectorized check
            malicious_mask = str_series.str.contains(self._MALICIOUS_PATTERN, regex=True, na=False)

            if malicious_mask.any():
                bad_values = [
                    val[:50] + "..." if len(val) > 50 else val for val in str_series[malicious_mask].unique()
                ]
                malicious[field] = bad_values

        return malicious
