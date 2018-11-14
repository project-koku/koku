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

"""View for update_charge endpoint."""

import logging

from flask import jsonify, request

from masu.processor.tasks import update_charge_info
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}

LOG = logging.getLogger(__name__)


@application_route('/update_charge/', API_V1_ROUTES, methods=('GET',))
def update_charge():
    """Update report summary tables in the database."""
    params = request.args

    provider_uuid = params.get('provider_uuid')
    schema_name = params.get('schema')

    if provider_uuid is None or schema_name is None:
        errmsg = 'provider_uuid and schema_name are required parameters.'
        return jsonify({'Error': errmsg}), 400

    LOG.info('Calling update_charge_info async task.')

    async_result = update_charge_info.delay(
        schema_name,
        provider_uuid,
    )

    return jsonify({'Update Charge Task ID': str(async_result)})
