#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the RBAC Service interaction."""
import logging
import os
from json.decoder import JSONDecodeError
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from prometheus_client import REGISTRY
from requests.exceptions import ConnectionError
from rest_framework import status

from koku.rbac import _apply_access
from koku.rbac import _get_operation
from koku.rbac import _process_acls
from koku.rbac import RbacConnectionError
from koku.rbac import RbacService


def create_expected_access(access_dict=None, default_write=None, default_read=None):
    """Helper function for defaulting access permissions."""
    if access_dict is None:
        access_dict = {}

    if default_write is None:
        default_write = {"write": [], "read": []}
    if default_read is None:
        default_read = {"read": []}

    default = {
        "cost_model": default_write,
        "settings": default_write,
        "aws.account": default_read,
        "aws.organizational_unit": default_read,
        "azure.subscription_guid": default_read,
        "gcp.account": default_read,
        "gcp.project": default_read,
        "openshift.cluster": default_read,
        "openshift.node": default_read,
        "openshift.project": default_read,
        "ibm.account": default_read,
    }
    return default | access_dict


LIMITED_AWS_ACCESS = {
    "permission": "cost-management:aws.account:read",
    "resourceDefinitions": [
        {"attributeFilter": {"key": "cost-management.aws.account", "operation": "equal", "value": "123456"}}
    ],
}


class MockResponse:
    """Mock response object for testing."""

    def __init__(self, json_data, status_code, exception=None):
        """Create object."""
        self.json_data = json_data
        self.status_code = status_code
        self.exception = exception

    def json(self):
        """Return json data."""
        if self.exception:
            raise self.exception
        return self.json_data


def mocked_requests_get_404_json(*args, **kwargs):
    """Mock invalid response that returns json."""
    json_response = {"details": "Invalid path."}
    return MockResponse(json_response, status.HTTP_404_NOT_FOUND)


def mocked_requests_get_404_text(*args, **kwargs):
    """Mock invalid response that returns non-json."""
    json_response = "Not JSON"
    return MockResponse(json_response, status.HTTP_404_NOT_FOUND)


def mocked_requests_get_404_except(*args, **kwargs):
    """Mock invalid response that returns non-json."""
    return MockResponse(None, status.HTTP_404_NOT_FOUND, JSONDecodeError("JSON Problem", "", 1))


def mocked_requests_get_500_text(*args, **kwargs):
    """Mock invalid response that returns non-json."""
    json_response = "Not JSON"
    return MockResponse(json_response, status.HTTP_500_INTERNAL_SERVER_ERROR)


def mocked_requests_get_200_text(*args, **kwargs):
    """Mock valid status response that returns non-json."""
    json_response = "Not JSON"
    return MockResponse(json_response, status.HTTP_200_OK)


def mocked_requests_get_200_except(*args, **kwargs):
    """Mock valid status response that raises an excecption."""
    return MockResponse(None, status.HTTP_200_OK, ValueError("Decode Problem"))


def mocked_requests_get_200_no_next(*args, **kwargs):
    """Mock valid status response that has no next."""
    json_response = {"links": {"next": None}, "data": [LIMITED_AWS_ACCESS]}
    return MockResponse(json_response, status.HTTP_200_OK)


def mocked_requests_get_200_no_next_ibm(*args, **kwargs):
    """Mock valid status response that has no next."""
    IBM = {"permission": "cost-management:ibm.account:*", "resourceDefinitions": []}
    json_response = {"links": {"next": None}, "data": [IBM]}
    return MockResponse(json_response, status.HTTP_200_OK)


def mocked_requests_get_200_next(*args, **kwargs):
    """Mock valid status response that has no next."""
    json_response = {"links": {"next": "/v1/access/?limit=10&offset=200"}, "data": [LIMITED_AWS_ACCESS]}
    if "limit" in args[0]:
        json_response["links"]["next"] = None

    return MockResponse(json_response, status.HTTP_200_OK)


def mocked_get_operation(access_item, res_type):
    """Mock value error for get operation."""
    raise ValueError("Invalid wildcard for invalid res type.")


class RbacServiceTest(TestCase):
    """Test RbacService object."""

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_404_json)
    def test_non_200_error_json(self, mock_get):
        """Test handling of request with non-200 response and json error."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_500_text)
    def test_500_error_json(self, mock_get):
        """Test handling of request with 500 response and json error."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        with self.assertRaises(RbacConnectionError):
            rbac._request_user_access(url, headers={})

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_404_text)
    def test_non_200_error_text(self, mock_get):
        """Test handling of request with non-200 response and non-json error."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_404_except)
    def test_non_200_error_except(self, mock_get):
        """Test handling of request with non-200 response and non-json error."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        logging.disable(logging.NOTSET)
        with self.assertLogs(logger="koku.rbac", level=logging.WARNING):
            access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_text)
    def test_200_text(self, mock_get):
        """Test handling of request with 200 response and non-json error."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_except)
    def test_200_exception(self, mock_get):
        """Test handling of request with 200 response and raises a json error."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_no_next)
    def test_200_all_results(self, mock_get):
        """Test handling of request with 200 response with no next link."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [LIMITED_AWS_ACCESS])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_next)
    def test_200_results_next(self, mock_get):
        """Test handling of request with 200 response with next link."""
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        access = rbac._request_user_access(url, headers={})
        self.assertEqual(access, [LIMITED_AWS_ACCESS, LIMITED_AWS_ACCESS])
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=ConnectionError("test exception"))
    def test_get_except(self, mock_get):
        """Test handling of request with ConnectionError."""
        before = REGISTRY.get_sample_value("rbac_connection_errors_total")
        rbac = RbacService()
        url = f"{rbac.protocol}://{rbac.host}:{rbac.port}{rbac.path}"
        with self.assertRaises(RbacConnectionError):
            rbac._request_user_access(url, headers={})
        after = REGISTRY.get_sample_value("rbac_connection_errors_total")
        self.assertEqual(1, after - before)
        mock_get.assert_called()

    def test_process_acls_bad_permission(self):
        """Test function of _process_acls with a bad permission format."""
        acls = [{"permission": "bad_permission"}]
        access = _process_acls(acls)
        self.assertIsNone(access)

    def test_process_acls_multiple(self):
        """Test function of _process_acls with a bad permission format."""
        acls = [
            {"permission": "cost-management:cost_model:read", "resourceDefinitions": []},
            {
                "permission": "cost-management:cost_model:write",
                "resourceDefinitions": [
                    {"attributeFilter": {"key": "cost-management.cost_model", "operation": "in", "value": "1,3,5"}}
                ],
            },
            {
                "permission": "cost-management:cost_model:write",
                "resourceDefinitions": [
                    {"attributeFilter": {"key": "cost-management.cost_model", "operation": "equal", "value": "8"}}
                ],
            },
        ]
        access = _process_acls(acls)
        expected = {
            "cost_model": [
                {"operation": "read", "resources": ["*"]},
                {"operation": "write", "resources": ["1", "3", "5"]},
                {"operation": "write", "resources": ["8"]},
            ]
        }
        self.assertEqual(access, expected)

    def test_process_acls_attributeFilter_value_list(self):
        """Test that we correctly handle a list of values."""
        acls = [
            {"permission": "cost-management:cost_model:read", "resourceDefinitions": []},
            {
                "permission": "cost-management:cost_model:write",
                "resourceDefinitions": [
                    {
                        "attributeFilter": {
                            "key": "cost-management.cost_model",
                            "operation": "in",
                            "value": ["1", "3", "5"],
                        }
                    }
                ],
            },
        ]
        access = _process_acls(acls)
        expected = {
            "cost_model": [
                {"operation": "read", "resources": ["*"]},
                {"operation": "write", "resources": ["1", "3", "5"]},
            ]
        }
        self.assertEqual(access, expected)

    def test_process_acls_rate_to_cost_model_substitution(self):
        """Test function of _process_acls with a bad permission format."""
        acls = [
            {"permission": "cost-management:rate:read", "resourceDefinitions": []},
            {
                "permission": "cost-management:rate:write",
                "resourceDefinitions": [
                    {"attributeFilter": {"key": "cost-management.rate", "operation": "in", "value": "1,3,5"}}
                ],
            },
            {
                "permission": "cost-management:rate:write",
                "resourceDefinitions": [
                    {"attributeFilter": {"key": "cost-management.rate", "operation": "equal", "value": "8"}}
                ],
            },
        ]
        access = _process_acls(acls)
        expected = {
            "cost_model": [
                {"operation": "read", "resources": ["*"]},
                {"operation": "write", "resources": ["1", "3", "5"]},
                {"operation": "write", "resources": ["8"]},
            ]
        }
        self.assertEqual(access, expected)

    def test_get_operation_invalid_res_type(self):
        """Test invalid resource type."""
        with self.assertRaises(ValueError):
            _get_operation({"operation": "*"}, "invalid")

    @patch("koku.rbac._get_operation", side_effect=mocked_get_operation)
    def test_apply_access_except(self, mock_get_operation):
        """Test handling exception _get_operation used in apply access method."""
        processed_acls = {"*": [{"operation": "*", "resources": ["1", "3"]}]}
        res_access = _apply_access(processed_acls)
        expected = create_expected_access()
        self.assertEqual(res_access, expected)
        mock_get_operation.assert_called()

    def test_apply_access_none(self):
        """Test handling none input for apply access method."""
        res_access = _apply_access(None)
        expected = create_expected_access()
        self.assertEqual(res_access, expected)

    def test_apply_access_all_wildcard(self):
        """Test handling of wildcard data for apply access method."""
        processed_acls = {"*": [{"operation": "*", "resources": ["1", "3"]}]}
        res_access = _apply_access(processed_acls)
        rw_access = {"write": ["1", "3"], "read": ["1", "3"]}
        read_access = {"read": ["1", "3"]}
        expected = create_expected_access(default_write=rw_access, default_read=read_access)
        self.assertEqual(res_access, expected)

    def test_apply_access_wildcard(self):
        """Test handling of wildcard data for apply access method."""
        processed_acls = {
            "*": [{"operation": "write", "resources": ["1", "3"]}, {"operation": "read", "resources": ["2"]}]
        }
        res_access = _apply_access(processed_acls)
        rw_access = {"write": ["1", "3"], "read": ["1", "3", "2"]}
        read_access = {"read": ["2"]}
        expected = create_expected_access(default_write=rw_access, default_read=read_access)
        self.assertEqual(res_access, expected)

    def test_apply_access_limited(self):
        """Test handling of limited resource access data for apply access method."""
        processed_acls = {
            "cost_model": [{"operation": "write", "resources": ["1", "3"]}, {"operation": "read", "resources": ["2"]}]
        }
        res_access = _apply_access(processed_acls)
        expected = create_expected_access({"cost_model": {"write": ["1", "3"], "read": ["1", "3", "2"]}})
        self.assertEqual(res_access, expected)

    def test_apply_access_for_openshift_clusteR_level(self):
        """Test handling of OpenShift Node/Project when only cluster role is set."""
        processed_acls = {"openshift.cluster": [{"operation": "read", "resources": ["2"]}]}
        res_access = _apply_access(processed_acls)
        expected = create_expected_access(
            {
                "openshift.cluster": {"read": ["2"]},
                "openshift.node": {"read": ["*"]},
                "openshift.project": {"read": ["*"]},
            }
        )
        self.assertEqual(res_access, expected)

    def test_apply_access_for_openshift_node_level(self):
        """Test handling of OpenShift Project when only node role is set."""
        processed_acls = {"openshift.node": [{"operation": "read", "resources": ["2"]}]}
        res_access = _apply_access(processed_acls)
        expected = create_expected_access(
            {
                "openshift.node": {"read": ["2"]},
                "openshift.project": {"read": ["*"]},
            }
        )
        self.assertEqual(res_access, expected)

    def test_apply_access_limited_no_read_write(self):
        """Test handling of limited resource access data for apply access method."""
        processed_acls = {}
        res_access = _apply_access(processed_acls)
        expected = create_expected_access()
        self.assertEqual(res_access, expected)

    def test_apply_case(self):
        """Test apply with mixed condition."""
        processed_acls = {
            "cost_model": [{"operation": "*", "resources": ["*"]}],
            "aws.account": [{"operation": "read", "resources": ["myaccount"]}],
        }
        res_access = _apply_access(processed_acls)
        expected = create_expected_access(
            {"cost_model": {"write": ["*"], "read": ["*"]}, "aws.account": {"read": ["myaccount"]}}
        )
        self.assertEqual(res_access, expected)

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_except)
    def test_get_access_for_user_none(self, mock_get):
        """Test handling of user request where no access returns None."""
        rbac = RbacService()
        mock_user = Mock()
        mock_user.identity_header = {"encoded": "dGVzdCBoZWFkZXIgZGF0YQ=="}
        access = rbac.get_access_for_user(mock_user)
        self.assertIsNone(access)
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_no_next)
    def test_get_access_for_user_data_limited(self, mock_get):
        """Test handling of user request where access returns data."""
        rbac = RbacService()
        mock_user = Mock()
        mock_user.identity_header = {"encoded": "dGVzdCBoZWFkZXIgZGF0YQ=="}
        access = rbac.get_access_for_user(mock_user)
        expected = create_expected_access({"aws.account": {"read": ["123456"]}})
        self.assertEqual(access, expected)
        mock_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_200_no_next_ibm)
    def test_get_access_for_user_data_limited_ibm(self, mock_get):
        """Test handling of user request where access returns data with IBM access."""
        rbac = RbacService()
        mock_user = Mock()
        mock_user.identity_header = {"encoded": "dGVzdCBoZWFkZXIgZGF0YQ=="}
        access = rbac.get_access_for_user(mock_user)
        expected = create_expected_access({"ibm.account": {"read": ["*"]}})
        self.assertEqual(access, expected)
        mock_get.assert_called()

    @patch.dict(os.environ, {"RBAC_CACHE_TTL": "5"})
    def test_get_cache_ttl(self):
        """Test to get the cache ttl value."""
        rbac = RbacService()
        self.assertEqual(rbac.get_cache_ttl(), 5)
