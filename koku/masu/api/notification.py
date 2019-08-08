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

from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.external.notification_handler import (NotificationHandler,
                                                NotificationHandlerError,
                                                NotificationHandlerFilter)
from masu.processor.orchestrator import Orchestrator

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

@api_view(http_method_names=['GET'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def post_notification(request):
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
