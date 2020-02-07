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

from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.config import Config
from masu.processor.orchestrator import Orchestrator

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def expired_data(request):
    """Return expired data."""
    simulate = True
    if request.method == "DELETE" and Config.DEBUG:
        simulate = False
    LOG.info("Simulate Flag: %s", simulate)

    orchestrator = Orchestrator()
    async_delete_results = orchestrator.remove_expired_report_data(simulate=simulate)
    response_key = "Async jobs for expired data removal"
    if simulate:
        response_key = response_key + " (simulated)"
    return Response({response_key: str(async_delete_results)})
