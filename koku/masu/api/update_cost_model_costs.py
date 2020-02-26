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
"""View for update_cost_model_costs endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.processor.tasks import update_cost_model_costs as cost_task

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def update_cost_model_costs(request):
    """Update report summary tables in the database."""
    params = request.query_params

    provider_uuid = params.get("provider_uuid")
    schema_name = params.get("schema")

    if provider_uuid is None or schema_name is None:
        errmsg = "provider_uuid and schema_name are required parameters."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    LOG.info("Calling update_cost_model_costs async task.")

    async_result = cost_task.delay(schema_name, provider_uuid)

    return Response({"Update Charge Task ID": str(async_result)})
