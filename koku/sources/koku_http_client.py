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
"""Koku HTTP Client."""
import requests
import json
from requests.exceptions import RequestException
from sources.config import Config


class KokuHTTPClientError(Exception):
    """KokuHTTPClient Error."""

    pass


class KokuHTTPClientNonRecoverableError(Exception):
    """KokuHTTPClient Unrecoverable Error."""

    pass


class KokuHTTPClient:
    """Koku HTTP client to create koku providers."""

    def __init__(self, auth_header):
        """Initialize the client."""
        self._base_url = Config.KOKU_API_URL
        header = {'x-rh-identity': auth_header, 'sources-client': 'True'}
        self._identity_header = header

    @staticmethod
    def _get_dict_from_text_field(value):
        try:
            db_dict = json.loads(value)
        except ValueError:
            db_dict = {}
        return db_dict

    def create_provider(self, name, provider_type, authentication, billing_source):
        """Koku HTTP call to create provider."""
        url = '{}/{}/'.format(self._base_url, 'providers')
        json_data = {'name': name, 'type': provider_type}
        auth_value = None
        if authentication.get('resource_name'):
            auth_value = authentication.get('resource_name')
            provider_resource_name = {'provider_resource_name': auth_value}
            json_data['authentication'] = provider_resource_name
        elif authentication.get('credentials'):
            auth_value = authentication.get('credentials')
            credential_name = {'credentials': auth_value}
            json_data['authentication'] = credential_name

        if billing_source.get('data_source'):
            billing_value = billing_source
            json_data['billing_source'] = billing_value
        elif billing_source.get('bucket'):
            bucket = {'bucket': billing_source.get('bucket')}
            json_data['billing_source'] = bucket
        else:
            json_data['billing_source'] = {'bucket': ''}
        try:
            r = requests.post(url, headers=self._identity_header, json=json_data)
        except RequestException as conn_err:
            raise KokuHTTPClientError('Failed to create provider. Connection Error: ', str(conn_err))
        if r.status_code != 201:
            raise KokuHTTPClientNonRecoverableError('Unable to create provider. Error: ', str(r.json()))
        return r.json()

    def destroy_provider(self, provider_uuid):
        """Koku HTTP call to destroy provider."""
        url = '{}/{}/{}/'.format(self._base_url, 'providers', provider_uuid)
        try:
            response = requests.delete(url, headers=self._identity_header)
        except RequestException as conn_err:
            raise KokuHTTPClientError('Failed to delete provider. Connection Error: ', str(conn_err))
        if response.status_code != 204:
            raise KokuHTTPClientError('Unable to remove koku provider. Response: ', str(response.status_code))
        return response
