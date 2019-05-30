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
"""Database source impelmentation to provide all CUR accounts for CURAccounts access."""

import requests

from masu.config import Config
from masu.exceptions import CURAccountsInterfaceError
from masu.external.accounts.cur_accounts_interface import CURAccountsInterface


def _verify_response(header):
    """
    Validate that the response header is of type application/json.

    Args:
        ({}) : header dictionary

    Returns:
        (Boolean) : True/False indicating whether or not the response is valid.

    """
    content_type = header.get('Content-Type')
    if content_type and content_type == 'application/json':
        return True

    return False


# pylint: disable=too-few-public-methods
class CURAccountsNetwork(CURAccountsInterface):
    """Provider interface defnition."""

    def __init__(self):
        """Initializer."""
        self.base_url = Config.KOKU_BASE_URL
        self.admin_user = Config.KOKU_ADMIN_USER
        self.admin_pass = Config.KOKU_ADMIN_PASS

    def _get_service_admin_token(self):
        """
        Retrieve service admin token from Koku.

        This will call koku's token-auth to get the service admin token.

        FIXME: We are using HTTP in the short term until we prove out the
        microservice design.  If we decide to move to the new microservice
        architecture then the security considerations should be considered
        such that masu and koku can trust each other and be able to establish
        adequate authentication between the two services.

        Args:
            None

        Returns:
            (String) : Service Admin token

        """
        token_auth_url = '{}/api/v1/token-auth/'.format(self.base_url)
        data = {'username': self.admin_user, 'password': self.admin_pass}

        try:
            response = requests.post(token_auth_url, data=data)
            if not _verify_response(response.headers):
                err_msg = ('Unexpected response. '
                           'Found Content: {}, Header: {}').format(response.content,
                                                                   response.headers)
                raise CURAccountsInterfaceError(err_msg)

            if response.status_code != requests.status_codes.codes.get('OK'):
                msg = 'Token Auth request return code: {}'.format(str(response.status_code))
                raise CURAccountsInterfaceError(msg)
        except requests.exceptions.RequestException as error:
            raise CURAccountsInterfaceError(str(error))

        response_dict = response.json()
        token = response_dict.get('token')
        return token

    def _build_service_admin_auth_header(self):
        """
        Construct the service admin Authentication header.

        Args:
            None

        Returns:
            ({}) : Authorization header. Example: {'Authorization': Token sdfsdfsd}

        """
        token = self._get_service_admin_token()
        token_value = 'Token {}'.format(token)
        header = {'Authorization': token_value}
        return header

    def get_accounts_from_source(self, provider_uuid=None):
        """
        Retrieve all accounts from the Koku database.

        This will return a list of dicts for the Orchestrator to use to access reports.

        Args:
            provider_uuid (String) - Optional, return specific account

        Returns:
            ([{}]) : A list of dicts

        """
        providers_url = '{}/api/v1/providers/'.format(self.base_url)

        try:
            response = requests.get(providers_url, headers=self._build_service_admin_auth_header())
        except requests.exceptions.RequestException as error:
            raise CURAccountsInterfaceError(str(error))

        if not _verify_response(response.headers):
            err_msg = ('Unexpected response. '
                       'Found Content: {}, Header: {}').format(response.content,
                                                               response.headers)
            raise CURAccountsInterfaceError(err_msg)

        all_providers = response.json().get('results')
        accounts = []
        for provider in all_providers:
            try:
                accounts.append({
                    'authentication': provider['authentication']['provider_resource_name'],
                    'billing_source': provider['billing_source']['bucket'],
                    'customer_name': provider['customer']['name'],
                    'provider_type': provider['type'],
                    'schema_name': provider['customer']['schema_name']
                })
            except KeyError as error:
                raise CURAccountsInterfaceError(str(error))
        return accounts
