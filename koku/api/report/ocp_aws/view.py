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

"""View for OCP Usage Reports."""

from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.settings import api_settings

from api.report.view import _generic_report


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def storage(request):
    """Get OCP on AWS storage usage data.

    @api {get} /api/v1/reports/inventory/ocp/storage Get memory usage data
    @apiName getOCPAWSInventoryStorageData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get OCP on AWS storage usage data.

    @apiHeader {String} token User authorization token.

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[project]=*

    @apiSuccess {Object} group_by  The grouping to applied to the report.
    @apiSuccess {Object} filter  The filter to applied to the report.
    @apiSuccess {Object} data  The report data.
    @apiSuccess {Object} total Aggregates statistics for the report range.
    @apiSuccessExample {json} Success-Response:

    """
    return _generic_report(request, report='storage', provider='ocp_aws')
