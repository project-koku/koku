#
# Copyright 2018 Red Hat, Inc.
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

"""Test the CURAccountsNetwork utility object."""

import responses
import requests
from masu.config import Config
from masu.exceptions import CURAccountsInterfaceError
from masu.external.accounts.network.cur_accounts_network import CURAccountsNetwork
from tests import MasuTestCase
from unittest.mock import patch


class CURAccountsNetworkTest(MasuTestCase):
    """Test Cases for the CURAccountsNetwork object."""

    def setUp(self):
        self.koku_host = Config.KOKU_HOST
        self.koku_port = str(Config.KOKU_PORT)
        self.admin_user = Config.KOKU_ADMIN_USER
        self.admin_pass = Config.KOKU_ADMIN_PASS
        self.mock_token = '6fafaf8db571349e75b1cb10511b294eb0fd0837'

    @responses.activate
    def test_get_service_admin_token(self):
        """Test to get the service admin token."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        accessor = CURAccountsNetwork()
        token = accessor._get_service_admin_token()
        self.assertEqual(token, self.mock_token)

    @patch('masu.config.Config.KOKU_BASE_URL', returns='http://www.fakekoku.io')
    def test_get_service_admin_token_network_error(self, mock_host):
        """Test to get the service admin token with a network error."""
        accessor = CURAccountsNetwork()
        with self.assertRaises(CURAccountsInterfaceError):
            accessor._get_service_admin_token()

    @responses.activate
    def test_get_service_admin_token_unexpected_response(self):
        """Test to get the service admin token with an unexpected response."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      body='sample text response',
                      headers={'Content-Type': 'text/plain'},
                      status=200)
        accessor = CURAccountsNetwork()
        with self.assertRaises(CURAccountsInterfaceError):
            accessor._get_service_admin_token()

    @responses.activate
    def test_get_service_admin_token_unexpected_error(self):
        """Test to get the service admin token with an unexpected error."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        accessor = CURAccountsNetwork()
        with patch.object(requests, 'post', side_effect=requests.exceptions.RequestException('err')):
            with self.assertRaises(CURAccountsInterfaceError):
                accessor._get_service_admin_token()

    @responses.activate
    def test_get_service_admin_token_non_200(self):
        """Test to get the service admin token with a non-200 response."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'error': 'not found'},
                      status=404)
        accessor = CURAccountsNetwork()
        with self.assertRaises(CURAccountsInterfaceError):
            accessor._get_service_admin_token()

    @responses.activate
    def test_build_service_admin_auth_header(self):
        """Test to build the SA Authentication header."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        accessor = CURAccountsNetwork()
        header = accessor._build_service_admin_auth_header()
        expected_header_value = 'Token {}'.format(self.mock_token)
        self.assertTrue('Authorization' in header.keys())
        self.assertEqual(header.get('Authorization'), expected_header_value)

    @responses.activate
    def test_get_accounts_from_source(self):
        """Test to get all accounts."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        mock_authentication = "arn:aws:iam::999999999999:role/CostManagement"
        mock_billing_source = "cost-usage-bucket"
        mock_customer_name = "acct10001"
        mock_provider_type = "AWS"
        mock_schema_name = "acct10001"

        mock_response = {
            "count": 1,
            "next": 'null',
            "previous": 'null',
            "results": [
                {
                    "authentication": {
                        "provider_resource_name": mock_authentication,
                        "uuid": "7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6"
                    },
                    "billing_source": {
                        "bucket": mock_billing_source,
                        "uuid": "75b17096-319a-45ec-92c1-18dbd5e78f94"
                    },
                    "created_by": {
                        "email": "test@example.com",
                        "username": "test_customer",
                        "uuid": "83c8098c-bd2f-4a45-a19d-4d8a43e1c816"
                    },
                    "customer": {
                        "date_created": "2018-07-20T13:55:46.798105Z",
                        "name": mock_customer_name,
                        "owner": {
                            "email": "test@example.com",
                            "username": "test_customer",
                            "uuid": "83c8098c-bd2f-4a45-a19d-4d8a43e1c816"
                        },
                        "schema_name": mock_schema_name,
                        "uuid": "0e1911ba-ec60-4656-96ea-39b60bd4c5d3"
                    },
                    "name": "Test Provider",
                    "type": mock_provider_type,
                    "uuid": "6e212746-484a-40cd-bba0-09a19d132d64"
                }
            ]
        }
        responses.add(responses.GET,
                'http://{}:{}/api/v1/providers/'.format(self.koku_host, self.koku_port),
                json=mock_response,
                status=200)
        accessor = CURAccountsNetwork()
        accounts = accessor.get_accounts_from_source()
        self.assertEqual(len(accounts), 1)
        account = accounts.pop()

        self.assertTrue('authentication' in account.keys())
        self.assertTrue('billing_source' in account.keys())
        self.assertTrue('customer_name' in account.keys())
        self.assertTrue('provider_type' in account.keys())
        self.assertTrue('schema_name' in account.keys())
        self.assertEqual(account.get('authentication'), mock_authentication)
        self.assertEqual(account.get('billing_source'), mock_billing_source)
        self.assertEqual(account.get('customer_name'), mock_customer_name)
        self.assertEqual(account.get('provider_type'), mock_provider_type)
        self.assertEqual(account.get('schema_name'), mock_schema_name)

    @responses.activate
    def test_get_accounts_from_source_unexpected_response(self):
        """Test to get all accounts with unexpected response."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        mock_authentication = "arn:aws:iam::999999999999:role/CostManagement"
        mock_billing_source = "cost-usage-bucket"
        mock_customer_name = "acct10001"
        mock_provider_type = "AWS"
        mock_schema_name = "acct10001"

        mock_response = {
            "count": 1,
            "next": 'null',
            "previous": 'null',
            "results": [
                {
                    "BAD_AUTHENTICATION": {
                        "provider_resource_name": mock_authentication,
                        "uuid": "7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6"
                    },
                    "billing_source": {
                        "bucket": mock_billing_source,
                        "uuid": "75b17096-319a-45ec-92c1-18dbd5e78f94"
                    },
                    "created_by": {
                        "email": "test@example.com",
                        "username": "test_customer",
                        "uuid": "83c8098c-bd2f-4a45-a19d-4d8a43e1c816"
                    },
                    "customer": {
                        "date_created": "2018-07-20T13:55:46.798105Z",
                        "name": mock_customer_name,
                        "owner": {
                            "email": "test@example.com",
                            "username": "test_customer",
                            "uuid": "83c8098c-bd2f-4a45-a19d-4d8a43e1c816"
                        },
                        "schema_name": mock_schema_name,
                        "uuid": "0e1911ba-ec60-4656-96ea-39b60bd4c5d3"
                    },
                    "name": "Test Provider",
                    "type": mock_provider_type,
                    "uuid": "6e212746-484a-40cd-bba0-09a19d132d64"
                }
            ]
        }
        responses.add(responses.GET,
                'http://{}:{}/api/v1/providers/'.format(self.koku_host, self.koku_port),
                json=mock_response,
                status=200)
        accessor = CURAccountsNetwork()
        with self.assertRaises(CURAccountsInterfaceError):
            accessor.get_accounts_from_source()

    @responses.activate
    @patch('masu.config.Config.KOKU_BASE_URL', returns='http://www.fakekoku.io')
    def test_get_accounts_from_source_network_error(self, mock_host):
        """Test to get all accounts with network error."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        # Don't mock the providers call
        accessor = CURAccountsNetwork()
        with self.assertRaises(CURAccountsInterfaceError):
            accessor.get_accounts_from_source()

    @responses.activate
    def test_get_accounts_from_source_response_error(self):
        """Test to get all accounts with response error."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)
        # Don't mock the providers call
        accessor = CURAccountsNetwork()
        with patch.object(requests, 'get', side_effect=requests.exceptions.RequestException('err')):
            with self.assertRaises(CURAccountsInterfaceError):
                accessor.get_accounts_from_source()

    @responses.activate
    def test_get_accounts_from_source_unexpected_type(self):
        """Test to get all accounts with non application/json response."""
        responses.add(responses.POST,
                      'http://{}:{}/api/v1/token-auth/'.format(self.koku_host, self.koku_port),
                      json={'token': self.mock_token},
                      status=200)

        responses.add(responses.GET,
                      'http://{}:{}/api/v1/providers/'.format(self.koku_host, self.koku_port),
                      body='sample text response',
                      headers={'Content-Type': 'text/plain'},
                      status=200)

        accessor = CURAccountsNetwork()
        with self.assertRaises(CURAccountsInterfaceError):
            accessor.get_accounts_from_source()
