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

"""View for report_data endpoint."""

import logging

from flask import jsonify, request

from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.tasks import (remove_expired_data,
                                  update_all_summary_tables,
                                  update_summary_tables)
from masu.util.blueprint import application_route

API_V1_ROUTES = {}
LOG = logging.getLogger('gunicorn.error')  # https://stackoverflow.com/a/34437443
REPORT_DATA_KEY = 'Report Data Task ID'


@application_route('/report_data/', API_V1_ROUTES, methods=('GET',))
def report_data():
    """Update report summary tables in the database."""
    params = request.args
    async_result = None
    all_providers = False
    provider_uuid = params.get('provider_uuid')
    provider_type = params.get('provider_type')
    schema_name = params.get('schema')
    start_date = params.get('start_date')
    end_date = params.get('end_date')

    if provider_uuid is None and provider_type is None:
        errmsg = 'provider_uuid or provider_type must be supplied as a parameter.'
        return jsonify({'Error': errmsg}), 400

    if provider_uuid == '*':
        all_providers = True
    elif provider_uuid:
        with ProviderDBAccessor(provider_uuid) as provider_accessor:
            provider = provider_accessor.get_type()
    else:
        provider = provider_type

    if start_date is None:
        errmsg = 'start_date is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if not all_providers:
        if schema_name is None:
            errmsg = 'schema is a required parameter.'
            return jsonify({'Error': errmsg}), 400

        if provider is None:
            errmsg = 'Unable to determine provider type.'
            return jsonify({'Error': errmsg}), 400

        if provider_type and provider_type != provider:
            errmsg = 'provider_uuid and provider_type have mismatched provider types.'
            return jsonify({'Error': errmsg}), 400

        async_result = update_summary_tables.delay(
            schema_name,
            provider,
            provider_uuid,
            start_date,
            end_date
        )
    else:
        async_result = update_all_summary_tables.delay(
            start_date,
            end_date
        )
    return jsonify({REPORT_DATA_KEY: str(async_result)})


@application_route('/report_data/', API_V1_ROUTES, methods=('DELETE',))
def remove_report_data():
    """Update report summary tables in the database."""
    params = request.args

    schema_name = params.get('schema')
    provider = params.get('provider')
    provider_id = params.get('provider_id')
    simulate = params.get('simulate')

    if schema_name is None:
        errmsg = 'schema is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if provider is None:
        errmsg = 'provider is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if provider_id is None:
        errmsg = 'provider_id is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if simulate is not None and simulate.lower() not in ('true', 'false'):
        errmsg = 'simulate must be a boolean.'
        return jsonify({'Error': errmsg}), 400

    # pylint: disable=simplifiable-if-statement
    if simulate is not None and simulate.lower() == 'true':
        simulate = True
    else:
        simulate = False

    LOG.info('Calling remove_expired_data async task.')

    async_result = remove_expired_data.delay(schema_name, provider, simulate,
                                             provider_id)

    return jsonify({'Report Data Task ID': str(async_result)})
