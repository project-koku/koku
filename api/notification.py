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

"""View for notification endpoint."""

import logging

from flask import request

from masu.external.notification_handler import (NotificationHandler,
                                                NotificationHandlerError,
                                                NotificationHandlerFilter)
from masu.processor.orchestrator import Orchestrator
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}


@application_route('/notification/', API_V1_ROUTES, methods=('POST',))
def post_notification():
    """Packages response for class-based view."""
    header_list = request.headers.to_wsgi_list()
    body = request.data.decode('utf-8')
    logger.debug('Received Header: %s', str(request.headers))
    logger.debug('Received Body: %s', str(body))
    notified_billing_source = None
    try:
        handler = NotificationHandler(header_list, body)
        notified_billing_source = handler.billing_source()
    except NotificationHandlerError as error:
        logger.error(str(error))
    except NotificationHandlerFilter as info:
        logger.info(str(info))

    if notified_billing_source:
        orchestrator = Orchestrator(notified_billing_source)
        orchestrator.prepare()

    return ('', 204)
