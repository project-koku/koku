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

from masu.processor.tasks import update_summary_tables
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}

LOG = logging.getLogger(__name__)


@application_route('/report_data/', API_V1_ROUTES, methods=('GET',))
def report_data():
    """Update report summary tables in the database."""
    params = request.args

    provider = params.get('provider')
    schema_name = params.get('schema')
    start_date = params.get('start_date')
    end_date = params.get('end_date')

    if provider is None:
        errmsg = 'provider is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if schema_name is None:
        errmsg = 'schema is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if start_date is None:
        errmsg = 'start_date is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    LOG.info('Calling update_summary_tables async task.')

    if end_date:
        async_result = update_summary_tables.delay(
            schema_name,
            provider,
            start_date,
            end_date
        )
    else:
        async_result = update_summary_tables.delay(schema_name, provider,
                                                   start_date)

    return jsonify({'Report Data Task ID': str(async_result)})
