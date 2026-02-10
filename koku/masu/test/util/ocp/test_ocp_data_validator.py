"""Tests for OCP data validation and sanitization utilities."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import pandas as pd

from masu.test import MasuTestCase
from masu.util.ocp.ocp_data_validator import OCPDataFrameAccessor
from masu.util.ocp.ocp_data_validator import OCPDataValidationError


class TestOCPDataFrameAccessor(MasuTestCase):
    """Tests for the OCP DataFrame accessor."""

    def setUp(self):
        """Set up test data."""
        # Import to register the accessor
        import masu.util.ocp.ocp_data_validator  # noqa: F401

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


class TestMaliciousContentDetection(TestOCPDataFrameAccessor):
    """Tests for malicious content detection."""

    def test_detects_sql_injection_patterns(self):
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
                df = pd.DataFrame({"namespace": [test_string]})
                self.assertTrue(
                    df.ocp.has_malicious_content(),
                    f"Expected SQL injection detection for: {test_string}",
                )

    def test_detects_xss_patterns(self):
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
                df = pd.DataFrame({"namespace": [test_string]})
                self.assertTrue(
                    df.ocp.has_malicious_content(),
                    f"Expected XSS detection for: {test_string}",
                )

    def test_allows_normal_strings(self):
        """Test that normal strings are not flagged as malicious."""
        normal_strings = [
            "my-namespace",
            "project-123",
            "app-frontend-v2",
            "cost-management",
            "openshift-monitoring",
            "node-exporter-abc123",
            "pvc-data-store",
            "storage-class-fast",
            "project-with-dashes",
            "app.frontend.v2",
            "cost_management",
            "description with spaces",
        ]
        for test_string in normal_strings:
            with self.subTest(test_string=test_string):
                df = pd.DataFrame({"namespace": [test_string]})
                self.assertFalse(
                    df.ocp.has_malicious_content(),
                    f"False positive for: {test_string}",
                )

    def test_get_malicious_fields(self):
        """Test get_malicious_fields returns correct structure."""
        malicious_fields = self.malicious_data.ocp.get_malicious_fields()
        self.assertIn("namespace", malicious_fields)
        self.assertIn("pod", malicious_fields)

        clean_fields = self.valid_data.ocp.get_malicious_fields()
        self.assertEqual(len(clean_fields), 0)


class TestDataFrameValidation(TestOCPDataFrameAccessor):
    """Tests for DataFrame validation."""

    def test_validate_valid_data(self):
        """Test validation of a DataFrame with valid data."""
        df, issues = self.valid_data.ocp.validate()
        self.assertEqual(len(issues), 0)
        pd.testing.assert_frame_equal(df, self.valid_data)

    def test_validate_detects_malicious_content(self):
        """Test that malicious content is detected."""
        df, issues = self.malicious_data.ocp.validate()
        self.assertGreater(len(issues), 0)

    def test_validate_detects_length_violations(self):
        """Test detection of length violations."""
        long_namespace = "a" * (OCPDataFrameAccessor.FIELD_MAX_LENGTHS["namespace"] + 10)
        df = pd.DataFrame(
            {
                "namespace": [long_namespace],
                "pod": ["pod-1"],
            }
        )
        _, issues = df.ocp.validate()
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("max length" in issue for issue in issues))

    def test_validate_handles_null_values(self):
        """Test that null values are handled correctly."""
        df = pd.DataFrame(
            {
                "namespace": ["project-1", None, "project-3"],
                "pod": ["pod-a", "pod-b", None],
            }
        )
        validated_df, issues = df.ocp.validate()
        self.assertEqual(len(issues), 0)


class TestDataFrameSanitization(TestOCPDataFrameAccessor):
    """Tests for DataFrame sanitization."""

    def test_sanitize_html_escapes_values(self):
        """Test that special characters are HTML escaped."""
        df = pd.DataFrame(
            {
                "namespace": ["<script>", "'test'", '"test"', "a&b"],
            }
        )
        sanitized = df.ocp.sanitize()
        values = sanitized["namespace"].tolist()

        self.assertIn("&lt;script&gt;", values)
        self.assertIn("&#x27;test&#x27;", values)
        self.assertIn("&quot;test&quot;", values)
        self.assertIn("a&amp;b", values)

    def test_sanitize_removes_null_bytes(self):
        """Test that null bytes are removed."""
        df = pd.DataFrame({"namespace": ["test\x00value"]})
        sanitized = df.ocp.sanitize()
        self.assertEqual(sanitized["namespace"].iloc[0], "testvalue")

    def test_sanitize_dataframe(self):
        """Test sanitization of DataFrame values."""
        df = self.malicious_data.copy().ocp.sanitize()

        # SQL injection string should be escaped
        namespace_values = df["namespace"].tolist()
        self.assertNotIn("'; DROP TABLE users; --", namespace_values)
        self.assertIn("&#x27;; DROP TABLE users; --", namespace_values)

        # XSS string should be escaped
        pod_values = df["pod"].tolist()
        self.assertNotIn("<script>alert('xss')</script>", pod_values)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", pod_values)


class TestValidateAndSanitize(TestOCPDataFrameAccessor):
    """Tests for combined validation and sanitization."""

    def test_validate_and_sanitize(self):
        """Test combined validation and sanitization."""
        df, issues = self.malicious_data.copy().ocp.validate_and_sanitize()

        # Should have detected issues
        self.assertGreater(len(issues), 0)

        # Data should be sanitized
        namespace_values = df["namespace"].tolist()
        self.assertNotIn("'; DROP TABLE users; --", namespace_values)

    def test_validate_and_sanitize_strict_mode(self):
        """Test that strict mode raises exception."""
        with self.assertRaises(OCPDataValidationError):
            self.malicious_data.copy().ocp.validate_and_sanitize(strict=True)

    def test_validate_and_sanitize_valid_data(self):
        """Test that valid data passes without issues."""
        df, issues = self.valid_data.copy().ocp.validate_and_sanitize()
        self.assertEqual(len(issues), 0)
