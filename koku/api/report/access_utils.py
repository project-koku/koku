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
"""Acess Handling for Reports."""
from django.core.exceptions import PermissionDenied

from api.report.queries import ReportQueryHandler


def _get_replacement_result(param_res_list, access_list, raise_exception=True):
    if ReportQueryHandler.has_wildcard(param_res_list):
        return access_list
    if not access_list and not raise_exception:
        return list(param_res_list)
    intersection = param_res_list & set(access_list)
    if not intersection:
        raise PermissionDenied()
    return list(intersection)


def _update_query_parameters(query_parameters, filter_key, access, access_key, raise_exception=True):
    """Alter query parameters based on user access."""
    access_list = access.get(access_key, {}).get('read', [])
    access_filter_applied = False
    if ReportQueryHandler.has_wildcard(access_list):
        return query_parameters

    # check group by
    group_by = query_parameters.get('group_by', {})
    if group_by.get(filter_key):
        items = set(group_by.get(filter_key))
        result = _get_replacement_result(items, access_list, raise_exception=True)
        if result:
            query_parameters['group_by'][filter_key] = result
            access_filter_applied = True

    if not access_filter_applied:
        if query_parameters.get('filter', {}).get(filter_key):
            items = set(query_parameters.get('filter', {}).get(filter_key))
            result = _get_replacement_result(items, access_list, raise_exception)
            if result:
                if query_parameters.get('filter') is None:
                    query_parameters['filter'] = {}
                query_parameters['filter'][filter_key] = result
        elif access_list:
            if query_parameters.get('filter') is None:
                query_parameters['filter'] = {}
            query_parameters['filter'][filter_key] = access_list

    return query_parameters


def update_query_parameters_for_aws(query_parameters, access):
    """Alter query parameters based on user access."""
    return _update_query_parameters(query_parameters, 'account', access, 'aws.account')


def update_query_parameters_for_azure(query_parameters, access):
    """Alter query parameters based on user access."""
    return _update_query_parameters(query_parameters, 'account', access, 'azure.subscription_guid')


def update_query_parameters_for_openshift(query_parameters, access):
    """Alter query parameters based on user access."""
    query_parameters = _update_query_parameters(query_parameters, 'cluster',
                                                access, 'openshift.cluster')
    query_parameters = _update_query_parameters(query_parameters, 'node', access,
                                                'openshift.node', raise_exception=False)
    query_parameters = _update_query_parameters(query_parameters, 'project', access,
                                                'openshift.project', raise_exception=False)
    return query_parameters
