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

from dateutil.parser import parse
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.utils import DateHelper
from masu.processor.tasks import update_cost_model_costs as cost_task

DH = DateHelper()
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
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    if provider_uuid is None or schema_name is None:
        errmsg = "provider_uuid and schema_name are required parameters."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    if start_date is None:
        start_date = str(DH.this_month_start())
    if end_date is None:
        end_date = str(DH.this_month_end())
    start_date = parse(start_date)
    end_date = parse(end_date)

    LOG.info("Calling update_cost_model_costs async task.")

    async_result = cost_task.delay(schema_name, provider_uuid, start_date, end_date)

    return Response({"Update Cost Model Cost Task ID": str(async_result)})
