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

from masu.external.accounts_accessor import AccountsAccessor
from masu.processor.report_processor import ReportProcessor
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}

LOG = logging.getLogger(__name__)


@application_route('/report_data/', API_V1_ROUTES, methods=('GET',))
def report_data():
    """Update report summary tables in the database."""
    params = request.args

    schema_name = params.get('schema')
    start_date = params.get('start_date')
    end_date = params.get('end_date')

    if schema_name is None:
        errmsg = 'schema is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    if start_date is None:
        errmsg = 'start_date is a required parameter.'
        return jsonify({'Error': errmsg}), 400

    for account in AccountsAccessor().get_accounts():
        if schema_name == account.get('schema_name'):
            LOG.info('Calling update_summary_tables.')
            provider = account.get('provider_type')
            processor = ReportProcessor(schema_name=schema_name,
                                        report_path='/doesnt/matter',
                                        compression='PLAIN',
                                        provider=provider)
            if end_date:
                async_result = processor.summarize_report_data(start_date, end_date)
            else:
                async_result = processor.summarize_report_data(start_date)

            return jsonify({'Report Data Task ID': str(async_result)})

    return jsonify({'Report Data Task ID': 'Unable to find account'})
