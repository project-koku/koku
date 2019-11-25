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
import json

import requests
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

    def _get_dict_from_text_field(self, value):
        try:
            db_dict = json.loads(value)
        except ValueError:
            db_dict = {}
        return db_dict

    def _build_provider_resource_name_auth(self, authentication):
        if authentication.get('resource_name'):
            auth = {'provider_resource_name': authentication.get('resource_name')}
        else:
            raise KokuHTTPClientError('Missing provider_resource_name')
        return auth

    def _build_credentials_auth(self, authentication):
        if authentication.get('credentials'):
            auth = {'credentials': authentication.get('credentials')}
        else:
            raise KokuHTTPClientError('Missing credentials')
        return auth

    def _authentication_for_aws(self, authentication):
        return self._build_provider_resource_name_auth(authentication)

    def _authentication_for_ocp(self, authentication):
        return self._build_provider_resource_name_auth(authentication)

    def _authentication_for_azure(self, authentication):
        return self._build_credentials_auth(authentication)

    def get_authentication_for_provider(self, provider_type, authentication):
        """Build authentication json data for provider type."""
        provider_map = {'AWS': self._authentication_for_aws,
                        'OCP': self._authentication_for_ocp,
                        'AZURE': self._authentication_for_azure}
        provider_fn = provider_map.get(provider_type)
        if provider_fn:
            return provider_fn(authentication)

    def _build_provider_bucket(self, billing_source):
        if billing_source.get('bucket') is not None:
            billing = {'bucket': billing_source.get('bucket')}
        else:
            raise KokuHTTPClientError('Missing bucket')
        return billing

    def _build_provider_data_source(self, billing_source):
        if billing_source.get('data_source'):
            billing = {'data_source': billing_source.get('data_source')}
        else:
            raise KokuHTTPClientError('Missing data_source')
        return billing

    def _billing_source_for_aws(self, billing_source):
        return self._build_provider_bucket(billing_source)

    def _billing_source_for_ocp(self, billing_source):
        billing_source['bucket'] = ''
        return self._build_provider_bucket(billing_source)

    def _billing_source_for_azure(self, billing_source):
        return self._build_provider_data_source(billing_source)

    def get_billing_source_for_provider(self, provider_type, billing_source):
        """Build billing source json data for provider type."""
        provider_map = {'AWS': self._billing_source_for_aws,
                        'OCP': self._billing_source_for_ocp,
                        'AZURE': self._billing_source_for_azure}
        provider_fn = provider_map.get(provider_type)
        if provider_fn:
            return provider_fn(billing_source)

    def _handle_bad_requests(self, response):
        """Raise an exception with error message string for Platform Sources."""
        if response.status_code == 401 or response.status_code == 403:
            raise KokuHTTPClientNonRecoverableError('Insufficient Permissions')
        if response.status_code == 400:
            detail_msg = 'Unknown Error'
            errors = response.json().get('errors')
            if errors:
                detail_msg = errors[0].get('detail')
            raise KokuHTTPClientNonRecoverableError(detail_msg)

    def create_provider(self, name, provider_type, authentication, billing_source, source_uuid=None):
        """Koku HTTP call to create provider."""
        url = '{}/{}/'.format(self._base_url, 'providers')
        json_data = {'name': name, 'type': provider_type,
                     'authentication': self.get_authentication_for_provider(provider_type,
                                                                            authentication),
                     'billing_source': self.get_billing_source_for_provider(provider_type,
                                                                            billing_source)}
        if source_uuid:
            json_data['uuid'] = str(source_uuid)
        try:
            r = requests.post(url, headers=self._identity_header, json=json_data)
        except RequestException as conn_err:
            raise KokuHTTPClientError('Failed to create provider. Connection Error: ', str(conn_err))
        self._handle_bad_requests(r)

        if r.status_code != 201:
            raise KokuHTTPClientNonRecoverableError(str(r.status_code))
        return r.json()

    def update_provider(self, provider_uuid, name, provider_type, authentication, billing_source):
        """Koku HTTP call to update provider."""
        url = '{}/{}/{}/'.format(self._base_url, 'providers', provider_uuid)
        json_data = {'name': name, 'type': provider_type,
                     'authentication': self.get_authentication_for_provider(provider_type,
                                                                            authentication),
                     'billing_source': self.get_billing_source_for_provider(provider_type,
                                                                            billing_source)}
        try:
            print(f'UPDATE JSON_DATA: {str(json_data)}')
            r = requests.put(url, headers=self._identity_header, json=json_data)
        except RequestException as conn_err:
            raise KokuHTTPClientError('Failed to create provider. Connection Error: ', str(conn_err))
        if r.status_code == 404:
            raise KokuHTTPClientNonRecoverableError('Provider not found. Error: ', str(r.json()))
        self._handle_bad_requests(r)

        if r.status_code != 200:
            raise KokuHTTPClientNonRecoverableError(str(r.status_code))
        return r.json()

    def destroy_provider(self, provider_uuid):
        """Koku HTTP call to destroy provider."""
        url = '{}/{}/{}/'.format(self._base_url, 'providers', provider_uuid)
        try:
            response = requests.delete(url, headers=self._identity_header)
        except RequestException as conn_err:
            raise KokuHTTPClientError('Failed to delete provider. Connection Error: ', str(conn_err))
        if response.status_code == 404:
            raise KokuHTTPClientNonRecoverableError('Provider not found. Error: ', str(response.json()))
        if response.status_code != 204:
            raise KokuHTTPClientError('Unable to remove koku provider. Status Code: ',
                                      str(response.status_code))
        return response
