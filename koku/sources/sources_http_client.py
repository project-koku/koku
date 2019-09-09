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
import requests


class SourcesHTTPClient:
    def __init__(self, auth_header, source_id=None):
        self._source_id = source_id
        self._sources_host = 'http://localhost:3000'
        self._base_url = '{}/{}'.format(self._sources_host, '/api/v1.0')
        self._internal_url = '{}/{}'.format(self._sources_host, '/internal/v1.0')

        header = {}
        header['x-rh-identity'] = auth_header
        self._identity_header = header

    def get_source_details(self):
        url = '{}/{}/{}'.format(self._base_url, 'sources', str(self._source_id))
        r = requests.get(url, headers=self._identity_header)
        response = r.json()
        return response

    def get_cost_management_application_type_id(self):
        application_type_url = '{}/application_types?filter[name]=/insights/platform/cost-management'.format(
            self._base_url)
        r = requests.get(application_type_url, headers=self._identity_header)
        endpoint_response = r.json()
        application_type_id = endpoint_response.get('data')[0].get('id')
        return int(application_type_id)

    def get_aws_role_arn(self):
        endpoint_url = '{}/endpoints?filter[source_id]={}'.format(self._base_url, str(self._source_id))
        r = requests.get(endpoint_url, headers=self._identity_header)
        endpoint_response = r.json()
        resource_id = endpoint_response.get('data')[0].get('id')

        authentications_url = \
            '{}/authentications?filter[resource_type]=Endpoint&[authtype]=arn&[resource_id]={}'.format(self._base_url,
                                                                                                       str(resource_id))
        r = requests.get(authentications_url, headers=self._identity_header)
        authentications_response = r.json()
        authentications_id = authentications_response.get('data')[0].get('id')

        authentications_internal_url = '{}/authentications/{}?expose_encrypted_attribute[]=password'.format(
            self._internal_url, str(authentications_id))
        r = requests.get(authentications_internal_url, headers=self._identity_header)
        authentications_internal_response = r.json()
        password = authentications_internal_response.get('password')

        return password
