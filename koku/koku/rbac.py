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
"""Interactions with the rbac service."""
import logging

import requests
from rest_framework import status

from api.query_handler import WILDCARD
from koku.env import ENVIRONMENT


LOGGER = logging.getLogger(__name__)
PROTOCOL = 'protocol'
HOST = 'host'
PORT = 'port'
PATH = 'path'
RESOURCE_TYPES = {
    'aws.account': ['read'],
    'openshift.cluster': ['read'],
    'openshift.node': ['read'],
    'openshift.project': ['read'],
    'provider': ['read', 'write'],
    'rate': ['read', 'write'],
}


def _extract_permission_data(permission):
    """Extract resource type and operation from permission."""
    perm_components = permission.split(':')
    if len(perm_components) != 3:
        raise ValueError('Invalid permission definition.')
    res_typ = perm_components[1]
    operation = perm_components[2]
    return (res_typ, operation)


def _extract_resource_definitions(resource_definitions):
    """Extract resource definition information."""
    result = []
    if resource_definitions == []:
        return [WILDCARD]
    for res_def in resource_definitions:
        att_filter = res_def.get('attributeFilter', {})
        operation = att_filter.get('operation')
        value = att_filter.get('value')
        if operation == 'equal' and value:
            result.append(value)
        if operation == 'in' and value:
            result += value.split(',')
    return result


def _process_acls(acls):
    """Process acls to determine capabilities."""
    access = {}
    for acl in acls:
        permission = acl.get('permission')
        resource_definitions = acl.get('resourceDefinitions', [])
        try:
            res_typ, operation = _extract_permission_data(permission)
            resources = _extract_resource_definitions(resource_definitions)
            acl_data = {
                'operation': operation,
                'resources': resources
            }
            if access.get(res_typ) is None:
                access[res_typ] = []
            access[res_typ].append(acl_data)
        except ValueError as exc:
            LOGGER.error('Skipping invalid ACL: %s', exc)
    if access == {}:
        return None
    return access


def _get_operation(access_item, res_type):
    """Get operation and default wildcard to write for now."""
    operation = access_item.get('operation')
    if operation == WILDCARD:
        operations = RESOURCE_TYPES.get(res_type, [])
        if operations:
            operation = operations[-1]
        else:
            LOGGER.error('Wildcard specified for invalid resource type - %s', res_type)
            raise ValueError('Invalid resource type: {}'.format(res_type))
    return operation


def _update_access_obj(access, res_access, resource_list):
    """Update access object with access data."""
    for res in resource_list:
        access_items = access.get(res, [])
        for access_item in access_items:
            operation = _get_operation(access_item, res)
            res_list = access_item.get('resources', [])
            if operation == 'write' and res_access[res].get('write') is not None:
                res_access[res]['write'] += res_list
                res_access[res]['read'] += res_list
            if operation == 'read':
                res_access[res]['read'] += res_list
    return res_access


def _apply_access(access):  # noqa: C901
    """Apply access to managed resources."""
    res_access = {}
    resources = []
    for res_type, operations in RESOURCE_TYPES.items():
        resources.append(res_type)
        for operation in operations:
            curr = res_access.get(res_type, {})
            curr[operation] = []
            res_access[res_type] = curr
    if access is None:
        return res_access

    # process '*' special case
    wildcard_items = access.get(WILDCARD, [])
    for wildcard_item in wildcard_items:
        res_list = wildcard_item.get('resources', [])
        try:
            for res_type in resources:
                operation = _get_operation(wildcard_item, res_type)
                acl = {'operation': operation, 'resources': res_list}
                curr_access = access.get(res_type, [])
                curr_access.append(acl)
                access[res_type] = curr_access
        except ValueError:
            pass

    res_access = _update_access_obj(access, res_access, resources)

    # compact down to only '*' if present
    for res_type, operations in RESOURCE_TYPES.items():
        resources.append(res_type)
        for operation in operations:
            curr = res_access.get(res_type, {})
            res_list = curr.get(operation)
            if any(WILDCARD == item for item in res_list):
                curr[operation] = [WILDCARD]
    return res_access


class RbacService:  # pylint: disable=too-few-public-methods
    """A class to handle interactions with the RBAC service."""

    def __init__(self):
        """Establish RBAC connection information."""
        rbac_conn_info = self._get_rbac_service()
        self.protocol = rbac_conn_info.get(PROTOCOL)
        self.host = rbac_conn_info.get(HOST)
        self.port = rbac_conn_info.get(PORT)
        self.path = rbac_conn_info.get(PATH)
        self.cache_ttl = int(ENVIRONMENT.get_value('RBAC_CACHE_TTL', default='30'))

    def _get_rbac_service(self):  # pylint: disable=no-self-use
        """Get RBAC service host and port info from environment."""
        rbac_conn_info = {
            PROTOCOL: ENVIRONMENT.get_value('RBAC_SERVICE_PROTOCOL', default='http'),
            HOST: ENVIRONMENT.get_value('RBAC_SERVICE_HOST', default='localhost'),
            PORT: ENVIRONMENT.get_value('RBAC_SERVICE_PORT', default='8111'),
            PATH: ENVIRONMENT.get_value('RBAC_SERVICE_PATH',
                                        default='/r/insights/platform/rbac/v1/access/')
        }
        return rbac_conn_info

    def _request_user_access(self, url, headers):
        """Send request to RBAC service and handle pagination case."""
        access = []
        response = requests.get(url, headers=headers)

        if response.status_code != status.HTTP_200_OK:
            try:
                error = response.json()
                LOGGER.error('Error requesting user access: %s', error)
            except ValueError as res_error:
                LOGGER.error('Error processing failed, %s, user access: %s',
                             response.status_code, res_error)
            return access

        # check for pagination handling
        try:
            data = response.json()
        except ValueError as res_error:
            LOGGER.error('Error processing user access: %s', res_error)
            return access

        if not isinstance(data, dict):
            LOGGER.error('Error processing user access. Unexpected response object: %s', data)
            return access

        next_link = data.get('links', {}).get('next')
        access = data.get('data', [])
        if next_link:
            next_url = '{}://{}:{}{}'.format(self.protocol, self.host, self.port, next_link)
            access += self._request_user_access(next_url, headers)
        return access

    def get_access_for_user(self, user):
        """Obtain access information for user."""
        url = '{}://{}:{}{}?application=cost-management&limit=100'.format(self.protocol,
                                                                          self.host,
                                                                          self.port,
                                                                          self.path)
        headers = {'x-rh-identity': user.identity_header.get('encoded')}
        acls = self._request_user_access(url, headers)
        if isinstance(acls, list) and len(acls) == 0:  # pylint: disable=len-as-condition
            return None

        processed_acls = _process_acls(acls)
        return _apply_access(processed_acls)

    def get_cache_ttl(self):
        """Return the cache time to live value."""
        return self.cache_ttl
