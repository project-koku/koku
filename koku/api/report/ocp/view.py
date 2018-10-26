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

"""View for Reports."""

from django.db.models import Value
from django.db.models.functions import Concat
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.settings import api_settings

from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPQueryParamSerializer
from api.report.view import _generic_report


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def memory(request):
    """Get memory usage data.

    @api {get} /api/v1/reports/ocp/memory/ Get memory data


    """
    extras = {'report_type': 'mem'}
    return _generic_report(request, OCPQueryParamSerializer, OCPReportQueryHandler, **extras)

@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def cpu(request):
    """Get cpu usage data.

    @api {get} /api/v1/reports/ocp/cpu/ Get cpu data

    http://localhost:8000/api/v1/reports/ocp/cpu/?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=5&group_by[cluster]=*
    """
    extras = {'report_type': 'cpu'}
    return _generic_report(request, OCPQueryParamSerializer, OCPReportQueryHandler, **extras)
