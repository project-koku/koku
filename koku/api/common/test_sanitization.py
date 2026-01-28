"""Tests for API output sanitization utilities."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.test import TestCase

from api.common.sanitization import OCP_USER_CONTROLLED_FIELDS
from api.common.sanitization import prepare_value_for_url_param
from api.common.sanitization import sanitize_api_response
from api.common.sanitization import sanitize_api_string_value
from api.common.sanitization import sanitize_dict_values
from api.common.sanitization import sanitize_for_html
from api.common.sanitization import sanitize_for_json_output
from api.common.sanitization import sanitize_for_url
from api.common.sanitization import sanitize_list_values


class TestSanitizeForHtml(TestCase):
    """Tests for HTML sanitization."""

    def test_sanitizes_script_tags(self):
        """Test that script tags are escaped."""
        result = sanitize_for_html("<script>alert('xss')</script>")
        self.assertEqual(result, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")

    def test_sanitizes_quotes(self):
        """Test that quotes are escaped."""
        result = sanitize_for_html('test"value')
        self.assertEqual(result, "test&quot;value")

        result = sanitize_for_html("test'value")
        self.assertEqual(result, "test&#x27;value")

    def test_sanitizes_ampersand(self):
        """Test that ampersand is escaped."""
        result = sanitize_for_html("a&b")
        self.assertEqual(result, "a&amp;b")

    def test_handles_non_strings(self):
        """Test that non-strings are returned unchanged."""
        self.assertIsNone(sanitize_for_html(None))
        self.assertEqual(sanitize_for_html(123), 123)
        self.assertEqual(sanitize_for_html(["list"]), ["list"])

    def test_handles_empty_string(self):
        """Test that empty strings are handled correctly."""
        self.assertEqual(sanitize_for_html(""), "")


class TestSanitizeForUrl(TestCase):
    """Tests for URL encoding."""

    def test_url_encodes_special_chars(self):
        """Test that special characters are URL encoded."""
        # Example from the issue: "'=0-- "
        result = sanitize_for_url("'=0-- ")
        self.assertEqual(result, "%27%3D0--%20")

    def test_url_encodes_spaces(self):
        """Test that spaces are encoded."""
        result = sanitize_for_url("my namespace")
        self.assertEqual(result, "my%20namespace")

    def test_url_encodes_slashes(self):
        """Test that slashes are encoded."""
        result = sanitize_for_url("project/name")
        self.assertEqual(result, "project%2Fname")

    def test_url_encodes_ampersands(self):
        """Test that ampersands are encoded."""
        result = sanitize_for_url("a&b")
        self.assertEqual(result, "a%26b")

    def test_handles_non_strings(self):
        """Test that non-strings are returned unchanged."""
        self.assertIsNone(sanitize_for_url(None))
        self.assertEqual(sanitize_for_url(123), 123)


class TestSanitizeForJsonOutput(TestCase):
    """Tests for JSON output sanitization."""

    def test_removes_null_bytes(self):
        """Test that null bytes are removed."""
        result = sanitize_for_json_output("test\x00value")
        self.assertEqual(result, "testvalue")

    def test_removes_control_characters(self):
        """Test that control characters are removed."""
        result = sanitize_for_json_output("test\x01\x02\x03value")
        self.assertEqual(result, "testvalue")

    def test_preserves_valid_content(self):
        """Test that valid content is preserved."""
        valid_string = "my-namespace-123"
        self.assertEqual(sanitize_for_json_output(valid_string), valid_string)

    def test_handles_non_strings(self):
        """Test that non-strings are returned unchanged."""
        self.assertIsNone(sanitize_for_json_output(None))
        self.assertEqual(sanitize_for_json_output(123), 123)


class TestSanitizeApiStringValue(TestCase):
    """Tests for combined API string sanitization."""

    def test_combines_sanitizations(self):
        """Test that multiple sanitization steps are applied."""
        # Contains both control char and HTML
        result = sanitize_api_string_value("<script>\x00</script>")
        self.assertEqual(result, "&lt;script&gt;&lt;/script&gt;")

    def test_sanitizes_xss_content(self):
        """Test that XSS content is sanitized."""
        result = sanitize_api_string_value("<img src=x onerror=alert('xss')>")
        self.assertNotIn("<img", result)
        self.assertIn("&lt;img", result)


class TestSanitizeDictValues(TestCase):
    """Tests for dictionary sanitization."""

    def test_sanitizes_known_fields(self):
        """Test that known user-controlled fields are sanitized."""
        data = {
            "namespace": "<script>xss</script>",
            "pod": "normal-pod",
            "cost": 100.50,
        }
        result = sanitize_dict_values(data)
        self.assertIn("&lt;script&gt;", result["namespace"])
        self.assertEqual(result["pod"], "normal-pod")
        self.assertEqual(result["cost"], 100.50)

    def test_does_not_sanitize_unknown_fields(self):
        """Test that unknown fields are not modified."""
        data = {
            "unknown_field": "<script>xss</script>",
            "namespace": "safe-namespace",
        }
        result = sanitize_dict_values(data)
        # unknown_field should not be sanitized by default
        self.assertEqual(result["unknown_field"], "<script>xss</script>")
        self.assertEqual(result["namespace"], "safe-namespace")

    def test_handles_nested_dicts(self):
        """Test that nested dictionaries are sanitized."""
        data = {
            "data": {
                "namespace": "<script>xss</script>",
            }
        }
        result = sanitize_dict_values(data)
        self.assertIn("&lt;script&gt;", result["data"]["namespace"])

    def test_handles_nested_lists(self):
        """Test that nested lists are sanitized."""
        data = {
            "items": [
                {"namespace": "<script>xss</script>"},
                {"namespace": "safe-namespace"},
            ]
        }
        result = sanitize_dict_values(data)
        self.assertIn("&lt;script&gt;", result["items"][0]["namespace"])
        self.assertEqual(result["items"][1]["namespace"], "safe-namespace")


class TestSanitizeListValues(TestCase):
    """Tests for list sanitization."""

    def test_sanitizes_list_of_dicts(self):
        """Test that a list of dictionaries is sanitized."""
        data = [
            {"namespace": "<script>xss</script>"},
            {"namespace": "safe-namespace"},
        ]
        result = sanitize_list_values(data)
        self.assertIn("&lt;script&gt;", result[0]["namespace"])
        self.assertEqual(result[1]["namespace"], "safe-namespace")

    def test_handles_empty_list(self):
        """Test that an empty list is handled."""
        result = sanitize_list_values([])
        self.assertEqual(result, [])


class TestPrepareValueForUrlParam(TestCase):
    """Tests for URL parameter preparation."""

    def test_prepares_malicious_value(self):
        """Test that malicious values are properly encoded for URLs."""
        # This is the value from the issue
        result = prepare_value_for_url_param("'=0-- ")
        self.assertEqual(result, "%27%3D0--%20")

    def test_handles_normal_values(self):
        """Test that normal values are encoded correctly."""
        result = prepare_value_for_url_param("my-namespace")
        # Simple alphanumeric with dash should be mostly preserved
        self.assertEqual(result, "my-namespace")

    def test_removes_control_chars_and_encodes(self):
        """Test that control characters are removed before encoding."""
        result = prepare_value_for_url_param("test\x00value")
        self.assertEqual(result, "testvalue")


class TestSanitizeApiResponse(TestCase):
    """Tests for full API response sanitization."""

    def test_sanitizes_nested_response(self):
        """Test sanitization of a nested API response structure."""
        response = {
            "data": [
                {
                    "project": "<script>xss</script>",
                    "cost": 100.50,
                    "values": [{"namespace": "'; DROP TABLE users; --"}],
                }
            ],
            "meta": {"count": 1},
        }
        result = sanitize_api_response(response)

        # project should be sanitized
        self.assertIn("&lt;script&gt;", result["data"][0]["project"])

        # cost should be unchanged
        self.assertEqual(result["data"][0]["cost"], 100.50)

        # nested namespace should be sanitized
        self.assertIn("&#x27;", result["data"][0]["values"][0]["namespace"])

        # meta should be unchanged
        self.assertEqual(result["meta"]["count"], 1)

    def test_url_encode_fields(self):
        """Test that specified fields are URL encoded instead of HTML escaped."""
        response = {
            "project": "'=0-- ",
            "namespace": "'=0-- ",
        }
        result = sanitize_api_response(response, url_encode_fields={"project"})

        # project should be URL encoded
        self.assertEqual(result["project"], "%27%3D0--%20")

        # namespace should be HTML escaped (not URL encoded)
        self.assertIn("&#x27;", result["namespace"])

    def test_handles_primitive_values(self):
        """Test that primitive values are returned unchanged."""
        self.assertEqual(sanitize_api_response("string"), "string")
        self.assertEqual(sanitize_api_response(123), 123)
        self.assertIsNone(sanitize_api_response(None))

    def test_ocp_user_controlled_fields_coverage(self):
        """Test that all OCP user-controlled fields are covered."""
        expected_fields = {
            "namespace",
            "project",
            "pod",
            "node",
            "cluster",
            "cluster_id",
            "cluster_alias",
            "persistentvolumeclaim",
            "persistentvolume",
            "storageclass",
            "resource_id",
        }
        self.assertEqual(OCP_USER_CONTROLLED_FIELDS, expected_fields)
