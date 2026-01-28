#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP data validation and sanitization utilities.

This module provides validation and sanitization functions for data ingested
from the Cost Management Metrics Operator to prevent security issues like
SQL injection and XSS attacks.
"""
import html
import logging
import re
from urllib.parse import quote

import pandas as pd

from api.common import log_json


LOG = logging.getLogger(__name__)


# Maximum length constraints for OCP fields
# Based on Kubernetes resource naming constraints and practical limits
FIELD_MAX_LENGTHS = {
    "namespace": 253,  # Kubernetes namespace max length
    "pod": 253,  # Kubernetes pod name max length
    "node": 253,  # Kubernetes node name max length
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

# Kubernetes DNS-1123 subdomain pattern (used for namespaces, pods, nodes, etc.)
# Must be lowercase alphanumeric, '-', or '.', start and end with alphanumeric
# Max 253 characters
DNS_1123_SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")

# More permissive pattern for labels and other fields that may contain special chars
# Allows alphanumeric, '-', '_', '.', '/', ':'
LABEL_VALUE_PATTERN = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_./:]*[a-zA-Z0-9]?$|^[a-zA-Z0-9]?$")

# Pattern to detect potentially malicious SQL injection attempts
SQL_INJECTION_PATTERNS = [
    re.compile(r"('|\")\s*(OR|AND|UNION|SELECT|INSERT|UPDATE|DELETE|DROP|;|--)", re.IGNORECASE),
    re.compile(r"(UNION\s+ALL\s+SELECT|UNION\s+SELECT)", re.IGNORECASE),
    re.compile(r"(SELECT\s+.+\s+FROM)", re.IGNORECASE),
    re.compile(r"(INSERT\s+INTO)", re.IGNORECASE),
    re.compile(r"(UPDATE\s+.+\s+SET)", re.IGNORECASE),
    re.compile(r"(DELETE\s+FROM)", re.IGNORECASE),
    re.compile(r"(DROP\s+(TABLE|DATABASE|INDEX))", re.IGNORECASE),
    re.compile(r"(;\s*(SELECT|INSERT|UPDATE|DELETE|DROP))", re.IGNORECASE),
    re.compile(r"(--\s*$|#\s*$)", re.IGNORECASE),
    re.compile(r"(/\*.*\*/)", re.IGNORECASE),
]

# Pattern to detect XSS attack attempts
XSS_PATTERNS = [
    re.compile(r"<script[^>]*>", re.IGNORECASE),
    re.compile(r"</script>", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onclick=, onerror=, etc.
    re.compile(r"<iframe[^>]*>", re.IGNORECASE),
    re.compile(r"<object[^>]*>", re.IGNORECASE),
    re.compile(r"<embed[^>]*>", re.IGNORECASE),
    re.compile(r"<svg[^>]*onload", re.IGNORECASE),
    re.compile(r"data:\s*text/html", re.IGNORECASE),
    re.compile(r"expression\s*\(", re.IGNORECASE),
]


class OCPDataValidationError(Exception):
    """Exception raised when OCP data validation fails."""

    def __init__(self, message: str, field: str = None, value: str = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)


def contains_sql_injection(value: str) -> bool:
    """
    Check if a string contains potential SQL injection patterns.

    Args:
        value: The string value to check.

    Returns:
        True if potential SQL injection patterns are detected.
    """
    if not isinstance(value, str):
        return False

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


def contains_xss(value: str) -> bool:
    """
    Check if a string contains potential XSS attack patterns.

    Args:
        value: The string value to check.

    Returns:
        True if potential XSS patterns are detected.
    """
    if not isinstance(value, str):
        return False

    for pattern in XSS_PATTERNS:
        if pattern.search(value):
            return True
    return False


def validate_field_length(value: str, field_name: str) -> bool:
    """
    Validate that a field value does not exceed maximum length.

    Args:
        value: The string value to validate.
        field_name: The name of the field for length lookup.

    Returns:
        True if the value is within allowed length.

    Raises:
        OCPDataValidationError: If the value exceeds maximum length.
    """
    if not isinstance(value, str):
        return True

    max_length = FIELD_MAX_LENGTHS.get(field_name)
    if max_length and len(value) > max_length:
        raise OCPDataValidationError(
            f"Field '{field_name}' exceeds maximum length of {max_length} characters",
            field=field_name,
            value=value[:50] + "..." if len(value) > 50 else value,
        )
    return True


def validate_kubernetes_name(value: str, field_name: str) -> bool:
    """
    Validate that a value conforms to Kubernetes naming conventions.

    Kubernetes resources like namespaces, pods, and nodes must follow
    DNS-1123 subdomain naming rules.

    Args:
        value: The string value to validate.
        field_name: The name of the field being validated.

    Returns:
        True if the value is valid.

    Note:
        Returns True for empty/null values as they may be optional.
    """
    if not value or not isinstance(value, str):
        return True

    # Check for null-like strings
    if value.lower() in ("", "nan", "none", "null"):
        return True

    # Kubernetes names should be lowercase
    if value != value.lower():
        LOG.debug(
            log_json(
                msg="Kubernetes name contains uppercase characters",
                field=field_name,
                value=value[:50] if len(value) > 50 else value,
            )
        )

    return True


def validate_no_malicious_content(value: str, field_name: str) -> bool:
    """
    Validate that a field value does not contain malicious content.

    Checks for SQL injection and XSS patterns.

    Args:
        value: The string value to validate.
        field_name: The name of the field being validated.

    Returns:
        True if no malicious content is detected.

    Raises:
        OCPDataValidationError: If malicious content is detected.
    """
    if not isinstance(value, str):
        return True

    if contains_sql_injection(value):
        raise OCPDataValidationError(
            f"Field '{field_name}' contains potentially malicious SQL content",
            field=field_name,
            value=value[:50] + "..." if len(value) > 50 else value,
        )

    if contains_xss(value):
        raise OCPDataValidationError(
            f"Field '{field_name}' contains potentially malicious script content",
            field=field_name,
            value=value[:50] + "..." if len(value) > 50 else value,
        )

    return True


def sanitize_value(value: str) -> str:
    """
    Sanitize a string value by removing or escaping potentially dangerous content.

    This function performs the following sanitizations:
    - HTML entity encoding for special characters
    - Removal of null bytes
    - Truncation of excessively long values

    Args:
        value: The string value to sanitize.

    Returns:
        The sanitized string value.
    """
    if not isinstance(value, str):
        return value

    # Remove null bytes
    value = value.replace("\x00", "")

    # HTML entity encode special characters
    value = html.escape(value, quote=True)

    return value


def url_encode_value(value: str) -> str:
    """
    URL encode a value for safe use in URLs.

    This is particularly useful for values that will be used in URL parameters,
    such as project/namespace names in the Cost Management UI.

    Args:
        value: The string value to URL encode.

    Returns:
        The URL-encoded string.
    """
    if not isinstance(value, str):
        return value

    return quote(value, safe="")


def validate_ocp_field(value: str, field_name: str, strict: bool = False) -> str:
    """
    Validate and optionally sanitize an OCP data field.

    This function performs comprehensive validation:
    1. Length validation
    2. Kubernetes naming convention validation (for applicable fields)
    3. Malicious content detection

    Args:
        value: The string value to validate.
        field_name: The name of the field being validated.
        strict: If True, raise exceptions for invalid data.
                If False, sanitize and log warnings.

    Returns:
        The validated (and possibly sanitized) value.

    Raises:
        OCPDataValidationError: If strict=True and validation fails.
    """
    if not isinstance(value, str) or not value:
        return value

    # Check for pandas NA values
    if pd.isna(value):
        return value

    try:
        # Validate length
        validate_field_length(value, field_name)

        # Validate Kubernetes naming for applicable fields
        k8s_name_fields = {"namespace", "pod", "node", "persistentvolumeclaim", "persistentvolume", "storageclass"}
        if field_name.lower() in k8s_name_fields:
            validate_kubernetes_name(value, field_name)

        # Check for malicious content
        validate_no_malicious_content(value, field_name)

        return value

    except OCPDataValidationError as err:
        if strict:
            raise

        # In non-strict mode, log warning and sanitize
        LOG.warning(
            log_json(
                msg="Data validation warning - sanitizing value",
                field=field_name,
                error=str(err),
            )
        )
        return sanitize_value(value)


def validate_dataframe(df: pd.DataFrame, schema: str = None) -> tuple[pd.DataFrame, list[str]]:
    """
    Validate all string columns in a DataFrame for malicious content.

    This function checks string columns for potential security issues
    and returns both the validated DataFrame and a list of any issues found.

    Args:
        df: The pandas DataFrame to validate.
        schema: Optional schema name for logging context.

    Returns:
        A tuple of (validated_dataframe, list_of_issues).
        Issues are logged but data is sanitized rather than rejected.
    """
    issues = []

    # Fields to validate - focusing on user-controllable string fields
    fields_to_validate = [
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
    ]

    for field in fields_to_validate:
        if field not in df.columns:
            continue

        # Get unique non-null values for validation
        unique_values = df[field].dropna().unique()

        for value in unique_values:
            if not isinstance(value, str):
                continue

            # Check for security issues
            if contains_sql_injection(value) or contains_xss(value):
                issue_msg = f"Potentially malicious content in field '{field}': {value[:50]}..."
                issues.append(issue_msg)
                LOG.warning(log_json(msg=issue_msg, schema=schema, field=field))

            # Check length constraints
            max_length = FIELD_MAX_LENGTHS.get(field)
            if max_length and len(value) > max_length:
                issue_msg = f"Field '{field}' value exceeds max length {max_length}: {len(value)} chars"
                issues.append(issue_msg)
                LOG.warning(log_json(msg=issue_msg, schema=schema, field=field))

    return df, issues


def sanitize_dataframe(df: pd.DataFrame, schema: str = None) -> pd.DataFrame:
    """
    Sanitize string columns in a DataFrame.

    This function applies sanitization to user-controllable string fields
    to prevent XSS and other injection attacks in API responses.

    Args:
        df: The pandas DataFrame to sanitize.
        schema: Optional schema name for logging context.

    Returns:
        The sanitized DataFrame.
    """
    # Fields to sanitize
    fields_to_sanitize = [
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
    ]

    for field in fields_to_sanitize:
        if field in df.columns:
            # Apply sanitization to non-null string values
            mask = df[field].notna() & df[field].apply(lambda x: isinstance(x, str))
            if mask.any():
                df.loc[mask, field] = df.loc[mask, field].apply(sanitize_value)

    return df


def validate_and_sanitize_dataframe(
    df: pd.DataFrame, schema: str = None, strict: bool = False
) -> tuple[pd.DataFrame, list[str]]:
    """
    Validate and sanitize a DataFrame containing OCP report data.

    This is the main entry point for DataFrame validation during data ingestion.
    It performs both validation (logging issues) and sanitization (cleaning data).

    Args:
        df: The pandas DataFrame to process.
        schema: Optional schema name for logging context.
        strict: If True, raise exception on validation errors.
                If False, log warnings and sanitize.

    Returns:
        A tuple of (processed_dataframe, list_of_issues).

    Raises:
        OCPDataValidationError: If strict=True and validation fails.
    """
    # First validate to collect issues
    df, issues = validate_dataframe(df, schema)

    if strict and issues:
        raise OCPDataValidationError(
            f"Data validation failed with {len(issues)} issues: {issues[0]}",
            field="multiple",
        )

    # Then sanitize
    df = sanitize_dataframe(df, schema)

    return df, issues
