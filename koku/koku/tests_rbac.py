#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the RBAC Service interaction."""
from unittest.mock import Mock, patch

from django.test import TestCase

from koku.rbac import RbacService, _apply_access, _get_operation, _process_acls


LIMITED_AWS_ACCESS = {
    'permission': 'cost-management:aws.account:read',
    'resourceDefinitions': [
        {
            'attributeFilter': {
                'key': 'cost-management.aws.account',
                'operation': 'equal',
                'value': '123456'
            }
        }
    ]
}


class MockResponse:  # pylint: disable=too-few-public-methods
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


def mocked_requests_get_404_json(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock invalid response that returns json."""
    json_response = {'details': 'Invalid path.'}
    return MockResponse(json_response, 404)


def mocked_requests_get_404_text(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock invalid response that returns non-json."""
    json_response = 'Not JSON'
    return MockResponse(json_response, 404)


def mocked_requests_get_404_except(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock invalid response that returns non-json."""
    return MockResponse(None, 404, ValueError('JSON Problem'))


def mocked_requests_get_200_text(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock valid status response that returns non-json."""
    json_response = 'Not JSON'
    return MockResponse(json_response, 200)


def mocked_requests_get_200_except(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock valid status response that raises an excecption."""
    return MockResponse(None, 200, ValueError('Decode Problem'))


def mocked_requests_get_200_no_next(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock valid status response that has no next."""
    json_response = {
        'links': {
            'next': None
        },
        'data': [LIMITED_AWS_ACCESS]
    }
    return MockResponse(json_response, 200)


def mocked_requests_get_200_next(*args, **kwargs):  # pylint: disable=unused-argument
    """Mock valid status response that has no next."""
    json_response = {
        'links': {
            'next': '/v1/access/?limit=10&offset=200'
        },
        'data': [LIMITED_AWS_ACCESS]
    }
    if 'limit' in args[0]:
        json_response['links']['next'] = None

    return MockResponse(json_response, 200)


def mocked_get_operation(access_item, res_type):  # pylint: disable=unused-argument
    """Mock value error for get operation."""
    raise ValueError('Invalid wildcard for invalid res type.')


class RbacServiceTest(TestCase):
    """Test RbacService object."""

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_404_json)
    def test_non_200_error_json(self, mock_get):
        """Test handling of request with non-200 response and json error."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_404_text)
    def test_non_200_error_text(self, mock_get):
        """Test handling of request with non-200 response and non-json error."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_404_except)
    def test_non_200_error_except(self, mock_get):
        """Test handling of request with non-200 response and non-json error."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_200_text)
    def test_200_text(self, mock_get):
        """Test handling of request with 200 response and non-json error."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_200_except)
    def test_200_exception(self, mock_get):
        """Test handling of request with 200 response and raises a json error."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [])
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_200_no_next)
    def test_200_all_results(self, mock_get):
        """Test handling of request with 200 response with no next link."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [LIMITED_AWS_ACCESS])
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_200_next)
    def test_200_results_next(self, mock_get):
        """Test handling of request with 200 response with next link."""
        rbac = RbacService()
        url = '{}://{}:{}{}'.format(rbac.protocol, rbac.host, rbac.port, rbac.path)
        access = rbac._request_user_access(url, headers={})  # pylint: disable=protected-access
        self.assertEqual(access, [LIMITED_AWS_ACCESS, LIMITED_AWS_ACCESS])
        mock_get.assert_called()

    def test_process_acls_bad_permission(self):
        """Test function of _process_acls with a bad permission format."""
        acls = [
            {
                'permission': 'bad_permission'
            }
        ]
        access = _process_acls(acls)  # pylint: disable=protected-access
        self.assertIsNone(access)

    def test_process_acls_multiple(self):
        """Test function of _process_acls with a bad permission format."""
        acls = [
            {
                'permission': 'cost-management:provider:read',
                'resourceDefinitions': []
            },
            {
                'permission': 'cost-management:provider:write',
                'resourceDefinitions': [{
                    'attributeFilter': {
                        'key': 'cost-management.provider',
                        'operation': 'in',
                        'value': '1,3,5'
                    }
                }]
            },
            {
                'permission': 'cost-management:provider:write',
                'resourceDefinitions': [{
                    'attributeFilter': {
                        'key': 'cost-management.provider',
                        'operation': 'equal',
                        'value': '8'
                    }
                }]
            }
        ]
        access = _process_acls(acls)  # pylint: disable=protected-access
        expected = {
            'provider': [
                {'operation': 'read', 'resources': ['*']},
                {'operation': 'write', 'resources': ['1', '3', '5']},
                {'operation': 'write', 'resources': ['8']}
            ]
        }
        print()
        print(access)
        self.assertEqual(access, expected)

    def test_get_operation_invalid_res_type(self):
        """Test invalid resource type."""
        with self.assertRaises(ValueError):
            _get_operation({'operation': '*'}, 'invalid')

    @patch('koku.rbac._get_operation', side_effect=mocked_get_operation)
    def test_apply_access_except(self, mock_get_operation):
        """Test handling exception _get_operation used in apply access method."""
        processed_acls = {'*': [
            {
                'operation': '*',
                'resources': ['1', '3']
            }
        ]}
        res_access = _apply_access(processed_acls)  # pylint: disable=protected-access
        rw_access = {'write': [], 'read': []}
        read_access = {'read': []}
        expected = {
            'provider': rw_access,
            'rate': rw_access,
            'aws.account': read_access,
            'openshift.cluster': read_access,
            'openshift.node': read_access,
            'openshift.project': read_access
        }
        self.assertEqual(res_access, expected)
        mock_get_operation.assert_called()

    def test_apply_access_none(self):
        """Test handling none input for apply access method."""
        res_access = _apply_access(None)  # pylint: disable=protected-access
        rw_access = {'write': [], 'read': []}
        read_access = {'read': []}
        expected = {
            'provider': rw_access,
            'rate': rw_access,
            'aws.account': read_access,
            'openshift.cluster': read_access,
            'openshift.node': read_access,
            'openshift.project': read_access
        }
        self.assertEqual(res_access, expected)

    def test_apply_access_all_wildcard(self):
        """Test handling of wildcard data for apply access method."""
        processed_acls = {'*': [
            {
                'operation': '*',
                'resources': ['1', '3']
            }
        ]}
        res_access = _apply_access(processed_acls)  # pylint: disable=protected-access
        rw_access = {'write': ['1', '3'], 'read': ['1', '3']}
        read_access = {'read': ['1', '3']}
        expected = {
            'provider': rw_access,
            'rate': rw_access,
            'aws.account': read_access,
            'openshift.cluster': read_access,
            'openshift.node': read_access,
            'openshift.project': read_access
        }
        self.assertEqual(res_access, expected)

    def test_apply_access_wildcard(self):
        """Test handling of wildcard data for apply access method."""
        processed_acls = {'*': [
            {
                'operation': 'write',
                'resources': ['1', '3']
            },
            {
                'operation': 'read',
                'resources': ['2']
            }
        ]}
        res_access = _apply_access(processed_acls)  # pylint: disable=protected-access
        rw_access = {'write': ['1', '3'], 'read': ['1', '3', '2']}
        read_access = {'read': ['2']}
        expected = {
            'provider': rw_access,
            'rate': rw_access,
            'aws.account': read_access,
            'openshift.cluster': read_access,
            'openshift.node': read_access,
            'openshift.project': read_access
        }
        self.assertEqual(res_access, expected)

    def test_apply_access_limited(self):
        """Test handling of limited resource access data for apply access method."""
        processed_acls = {'provider': [
            {
                'operation': 'write',
                'resources': ['1', '3']
            },
            {
                'operation': 'read',
                'resources': ['2']
            }
        ]}
        res_access = _apply_access(processed_acls)  # pylint: disable=protected-access
        op_access = {'write': ['1', '3'], 'read': ['1', '3', '2']}
        no_rw_access = {'write': [], 'read': []}
        no_access = {'read': []}
        expected = {
            'provider': op_access,
            'rate': no_rw_access,
            'aws.account': no_access,
            'openshift.cluster': no_access,
            'openshift.node': no_access,
            'openshift.project': no_access
        }
        self.assertEqual(res_access, expected)

    def test_apply_case(self):
        """Test apply with mixed condition."""
        processed_acls = {
            'provider': [{'operation': '*', 'resources': ['*']}],
            'rate': [{'operation': '*', 'resources': ['*']}],
            'aws.account': [{'operation': 'read', 'resources': ['myaccount']}]
        }
        res_access = _apply_access(processed_acls)  # pylint: disable=protected-access
        op_access = {'read': ['myaccount']}
        rw_access = {'write': ['*'], 'read': ['*']}
        no_access = {'read': []}
        expected = {
            'provider': rw_access,
            'rate': rw_access,
            'aws.account': op_access,
            'openshift.cluster': no_access,
            'openshift.node': no_access,
            'openshift.project': no_access
        }
        self.assertEqual(res_access, expected)

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_200_except)
    def test_get_access_for_user_none(self, mock_get):
        """Test handling of user request where no access returns None."""
        rbac = RbacService()
        mock_user = Mock()
        mock_user.identity_header = {'encoded': 'dGVzdCBoZWFkZXIgZGF0YQ=='}
        access = rbac.get_access_for_user(mock_user)
        self.assertIsNone(access)
        mock_get.assert_called()

    @patch('koku.rbac.requests.get', side_effect=mocked_requests_get_200_no_next)
    def test_get_access_for_user_data_limited(self, mock_get):
        """Test handling of user request where access returns data."""
        rbac = RbacService()
        mock_user = Mock()
        mock_user.identity_header = {'encoded': 'dGVzdCBoZWFkZXIgZGF0YQ=='}
        access = rbac.get_access_for_user(mock_user)
        expected = {
            'provider': {'write': [], 'read': []},
            'rate': {'write': [], 'read': []},
            'aws.account': {'read': ['123456']},
            'openshift.cluster': {'read': []},
            'openshift.node': {'read': []},
            'openshift.project': {'read': []}
        }
        self.assertEqual(access, expected)
        mock_get.assert_called()
