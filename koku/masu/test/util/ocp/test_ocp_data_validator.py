"""Tests for OCP data validation and sanitization utilities."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import pandas as pd

from masu.test import MasuTestCase
from masu.util.ocp.ocp_data_validator import contains_sql_injection
from masu.util.ocp.ocp_data_validator import contains_xss
from masu.util.ocp.ocp_data_validator import FIELD_MAX_LENGTHS
from masu.util.ocp.ocp_data_validator import OCPDataValidationError
from masu.util.ocp.ocp_data_validator import sanitize_dataframe
from masu.util.ocp.ocp_data_validator import sanitize_value
from masu.util.ocp.ocp_data_validator import url_encode_value
from masu.util.ocp.ocp_data_validator import validate_and_sanitize_dataframe
from masu.util.ocp.ocp_data_validator import validate_dataframe
from masu.util.ocp.ocp_data_validator import validate_field_length
from masu.util.ocp.ocp_data_validator import validate_no_malicious_content
from masu.util.ocp.ocp_data_validator import validate_ocp_field


class TestOCPDataValidator(MasuTestCase):
    """Tests for OCP data validation functions."""

    def test_contains_sql_injection_detects_basic_patterns(self):
        """Test that SQL injection patterns are detected."""
        sql_injection_strings = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "1 UNION SELECT * FROM users",
            "'; INSERT INTO users VALUES ('hacker'); --",
            "' OR 1=1--",
            "1; DELETE FROM users",
            "admin'--",
            "1 UNION ALL SELECT username, password FROM users",
            "'; UPDATE users SET admin=1; --",
        ]
        for test_string in sql_injection_strings:
            with self.subTest(test_string=test_string):
                self.assertTrue(
                    contains_sql_injection(test_string),
                    f"Expected SQL injection detection for: {test_string}",
                )

    def test_contains_sql_injection_allows_normal_strings(self):
        """Test that normal strings are not flagged as SQL injection."""
        normal_strings = [
            "my-namespace",
            "project-123",
            "app-frontend-v2",
            "cost-management",
            "openshift-monitoring",
            "node-exporter-abc123",
            "pvc-data-store",
            "storage-class-fast",
        ]
        for test_string in normal_strings:
            with self.subTest(test_string=test_string):
                self.assertFalse(
                    contains_sql_injection(test_string),
                    f"False positive SQL injection for: {test_string}",
                )

    def test_contains_sql_injection_handles_non_strings(self):
        """Test that non-string values return False."""
        self.assertFalse(contains_sql_injection(None))
        self.assertFalse(contains_sql_injection(123))
        self.assertFalse(contains_sql_injection(["list"]))

    def test_contains_xss_detects_basic_patterns(self):
        """Test that XSS patterns are detected."""
        xss_strings = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<iframe src='evil.com'></iframe>",
            "<svg onload=alert('xss')>",
            "<object data='evil.swf'></object>",
            "<embed src='evil.swf'></embed>",
            "data:text/html,<script>alert('xss')</script>",
            "onclick=alert('xss')",
        ]
        for test_string in xss_strings:
            with self.subTest(test_string=test_string):
                self.assertTrue(
                    contains_xss(test_string),
                    f"Expected XSS detection for: {test_string}",
                )

    def test_contains_xss_allows_normal_strings(self):
        """Test that normal strings are not flagged as XSS."""
        normal_strings = [
            "my-namespace",
            "project-with-dashes",
            "app.frontend.v2",
            "cost_management",
            "openshift-monitoring",
            "description with spaces",
        ]
        for test_string in normal_strings:
            with self.subTest(test_string=test_string):
                self.assertFalse(
                    contains_xss(test_string),
                    f"False positive XSS for: {test_string}",
                )

    def test_contains_xss_handles_non_strings(self):
        """Test that non-string values return False."""
        self.assertFalse(contains_xss(None))
        self.assertFalse(contains_xss(123))
        self.assertFalse(contains_xss(["list"]))

    def test_validate_field_length_valid(self):
        """Test that valid length values pass validation."""
        # Namespace max is 253
        self.assertTrue(validate_field_length("a" * 253, "namespace"))
        self.assertTrue(validate_field_length("short", "namespace"))
        self.assertTrue(validate_field_length("", "namespace"))

    def test_validate_field_length_invalid(self):
        """Test that exceeding max length raises an error."""
        with self.assertRaises(OCPDataValidationError) as context:
            validate_field_length("a" * 300, "namespace")
        self.assertIn("namespace", str(context.exception))
        self.assertIn("253", str(context.exception))

    def test_validate_field_length_unknown_field(self):
        """Test that unknown fields pass validation."""
        # Unknown fields should pass (no max length defined)
        self.assertTrue(validate_field_length("a" * 1000, "unknown_field"))

    def test_validate_no_malicious_content_valid(self):
        """Test that clean values pass validation."""
        clean_values = [
            "my-namespace",
            "project-123",
            "app.frontend.v2",
        ]
        for value in clean_values:
            with self.subTest(value=value):
                self.assertTrue(validate_no_malicious_content(value, "namespace"))

    def test_validate_no_malicious_content_sql_injection(self):
        """Test that SQL injection is caught."""
        with self.assertRaises(OCPDataValidationError) as context:
            validate_no_malicious_content("'; DROP TABLE users; --", "namespace")
        self.assertIn("malicious SQL", str(context.exception))

    def test_validate_no_malicious_content_xss(self):
        """Test that XSS is caught."""
        with self.assertRaises(OCPDataValidationError) as context:
            validate_no_malicious_content("<script>alert('xss')</script>", "namespace")
        self.assertIn("malicious script", str(context.exception))

    def test_sanitize_value_html_escapes(self):
        """Test that special characters are HTML escaped."""
        test_cases = [
            ("<script>", "&lt;script&gt;"),
            ("'test'", "&#x27;test&#x27;"),
            ('"test"', "&quot;test&quot;"),
            ("a&b", "a&amp;b"),
        ]
        for input_val, expected in test_cases:
            with self.subTest(input_val=input_val):
                self.assertEqual(sanitize_value(input_val), expected)

    def test_sanitize_value_removes_null_bytes(self):
        """Test that null bytes are removed."""
        self.assertEqual(sanitize_value("test\x00value"), "testvalue")

    def test_sanitize_value_handles_non_strings(self):
        """Test that non-string values are returned unchanged."""
        self.assertIsNone(sanitize_value(None))
        self.assertEqual(sanitize_value(123), 123)

    def test_url_encode_value(self):
        """Test URL encoding of values."""
        test_cases = [
            ("'=0-- ", "%27%3D0--%20"),
            ("my namespace", "my%20namespace"),
            ("test&value", "test%26value"),
            ("project/name", "project%2Fname"),
        ]
        for input_val, expected in test_cases:
            with self.subTest(input_val=input_val):
                self.assertEqual(url_encode_value(input_val), expected)

    def test_url_encode_value_handles_non_strings(self):
        """Test that non-string values are returned unchanged."""
        self.assertIsNone(url_encode_value(None))
        self.assertEqual(url_encode_value(123), 123)

    def test_validate_ocp_field_valid(self):
        """Test validation of valid OCP field values."""
        valid_values = [
            ("my-namespace", "namespace"),
            ("pod-123", "pod"),
            ("node-abc", "node"),
        ]
        for value, field in valid_values:
            with self.subTest(value=value, field=field):
                result = validate_ocp_field(value, field)
                self.assertEqual(result, value)

    def test_validate_ocp_field_strict_mode(self):
        """Test that strict mode raises exception on invalid data."""
        with self.assertRaises(OCPDataValidationError):
            validate_ocp_field("'; DROP TABLE users; --", "namespace", strict=True)

    def test_validate_ocp_field_non_strict_sanitizes(self):
        """Test that non-strict mode sanitizes instead of raising."""
        result = validate_ocp_field("<script>alert('xss')</script>", "namespace", strict=False)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_validate_ocp_field_handles_empty_values(self):
        """Test that empty values are handled correctly."""
        self.assertEqual(validate_ocp_field("", "namespace"), "")
        self.assertIsNone(validate_ocp_field(None, "namespace"))


class TestDataFrameValidation(MasuTestCase):
    """Tests for DataFrame validation functions."""

    def setUp(self):
        """Set up test data."""
        self.valid_data = pd.DataFrame(
            {
                "namespace": ["project-1", "project-2", "project-3"],
                "pod": ["pod-a", "pod-b", "pod-c"],
                "node": ["node-1", "node-2", "node-3"],
                "pod_usage_cpu_core_seconds": [100, 200, 300],
            }
        )

        self.malicious_data = pd.DataFrame(
            {
                "namespace": ["project-1", "'; DROP TABLE users; --", "project-3"],
                "pod": ["pod-a", "<script>alert('xss')</script>", "pod-c"],
                "node": ["node-1", "node-2", "node-3"],
                "pod_usage_cpu_core_seconds": [100, 200, 300],
            }
        )

    def test_validate_dataframe_valid_data(self):
        """Test validation of a DataFrame with valid data."""
        df, issues = validate_dataframe(self.valid_data, schema="test_schema")
        self.assertEqual(len(issues), 0)
        pd.testing.assert_frame_equal(df, self.valid_data)

    def test_validate_dataframe_detects_malicious_content(self):
        """Test that malicious content is detected."""
        df, issues = validate_dataframe(self.malicious_data, schema="test_schema")
        self.assertGreater(len(issues), 0)

    def test_sanitize_dataframe(self):
        """Test sanitization of DataFrame values."""
        df = sanitize_dataframe(self.malicious_data.copy(), schema="test_schema")

        # SQL injection string should be escaped
        namespace_values = df["namespace"].tolist()
        self.assertNotIn("'; DROP TABLE users; --", namespace_values)
        self.assertIn("&#x27;; DROP TABLE users; --", namespace_values)

        # XSS string should be escaped
        pod_values = df["pod"].tolist()
        self.assertNotIn("<script>alert('xss')</script>", pod_values)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", pod_values)

    def test_validate_and_sanitize_dataframe(self):
        """Test combined validation and sanitization."""
        df, issues = validate_and_sanitize_dataframe(self.malicious_data.copy(), schema="test_schema", strict=False)

        # Should have detected issues
        self.assertGreater(len(issues), 0)

        # Data should be sanitized
        namespace_values = df["namespace"].tolist()
        self.assertNotIn("'; DROP TABLE users; --", namespace_values)

    def test_validate_and_sanitize_dataframe_strict_mode(self):
        """Test that strict mode raises exception."""
        with self.assertRaises(OCPDataValidationError):
            validate_and_sanitize_dataframe(self.malicious_data.copy(), schema="test_schema", strict=True)

    def test_validate_dataframe_length_violations(self):
        """Test detection of length violations."""
        long_namespace = "a" * (FIELD_MAX_LENGTHS["namespace"] + 10)
        df = pd.DataFrame(
            {
                "namespace": [long_namespace],
                "pod": ["pod-1"],
            }
        )
        _, issues = validate_dataframe(df, schema="test_schema")
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("max length" in issue for issue in issues))

    def test_validate_dataframe_handles_null_values(self):
        """Test that null values are handled correctly."""
        df = pd.DataFrame(
            {
                "namespace": ["project-1", None, "project-3"],
                "pod": ["pod-a", "pod-b", None],
            }
        )
        validated_df, issues = validate_dataframe(df, schema="test_schema")
        self.assertEqual(len(issues), 0)
