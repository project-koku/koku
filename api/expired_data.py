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

"""View for expired_data endpoint."""

import logging

from flask import jsonify, request

from masu.config import Config
from masu.external.accounts_accessor import (AccountsAccessor, AccountsAccessorError)
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}

LOG = logging.getLogger(__name__)


@application_route('/expired_data/', API_V1_ROUTES, methods=('GET', 'DELETE'))
def expired_data():
    """Return expired data."""
    simulate = True
    if request.method == 'DELETE' and Config.DEBUG:
        simulate = False
    LOG.info('Simulate Flag: %s', simulate)

    removed_data = []
    try:
        for account in AccountsAccessor().get_accounts():
            LOG.info('Attempting to remove expired data for %s', account.get('customer_name'))
            remover = ExpiredDataRemover(account.get('schema_name'))
            removed_data = remover.remove(simulate=simulate)
    except AccountsAccessorError as error:
        LOG.error('Unable to get accounts. Error: %s', str(error))

    status_msg = 'Expired Data' if simulate else 'Removed Data'
    return jsonify({status_msg: str(removed_data)})
