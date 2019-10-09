#
# Copyright 2019 Red Hat, Inc.
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
"""Azure views."""

from api.common.permissions.azure_access import AzureAccessPermission
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.azure.serializers import AzureQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.azure.models import AzureTagsSummary


class AzureView(ReportView):
    """Azure Base View."""

    permission_classes = [AzureAccessPermission]
    provider = 'AZURE'
    serializer = AzureQueryParamSerializer
    query_handler = AzureReportQueryHandler
    tag_handler = [AzureTagsSummary]


class AzureCostView(AzureView):
    """Get cost data.

    @api {get} /cost-management/v1/reports/azure/costs/ Get cost data
    @apiName getAzureCostData
    @apiGroup Azure Report
    @apiVersion 1.0.0
    @apiDescription Get cost data.

    @apiHeader {String} token User authorization token.
    @apiHeader {String} accept HTTP Accept header. (See: RFC2616)
    @apiHeaderExample {json} Header-Example:
        {
            "Accept": "text/csv;q=0.8, application/json"
        }

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope_value]=-10&order_by[cost]=asc

    @apiSuccess {Object} group_by  The grouping to applied to the report.
    @apiSuccess {Object} order_by  The ordering to applied to the report
    @apiSuccess {Object} filter  The filter to applied to the report.
    @apiSuccess {Object} data  The report data.
    @apiSuccessExample {json} Success-Response:
        HTTP/1.1 200 OK
        {
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK

    """

    report = 'costs'


class AzureInstanceTypeView(AzureView):
    """Get inventory data.

    @api {get} /cost-management/v1/reports/azure/instance-types/ Get inventory instance type data
    @apiName getAzureInstanceTypeData
    @apiGroup Azure Report
    @apiVersion 1.0.0
    @apiDescription Get inventory instance type data.

    @apiHeader {String} token User authorization token.
    @apiHeader {String} accept HTTP Accept header. (See: RFC2616)
    @apiHeaderExample {json} Header-Example:
        {
            "Accept": "text/csv;q=0.8, application/json"
        }

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParam (Query Param) {String} units The units used in the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope_value]=-10&order_by[cost]=asc&group_by[account]=*&units=hours

    @apiSuccess {Object} group_by  The grouping to applied to the report.
    @apiSuccess {Object} filter  The filter to applied to the report.
    @apiSuccess {Object} data  The data including types, usage, and distinct number of instances for a time period.
    @apiSuccess {Object} total Aggregates statistics for the report range.
    @apiSuccessExample {json} Success-Response:
        HTTP/1.1 200 OK
        {
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK

    """

    report = 'instance_type'


class AzureStorageView(AzureView):
    """Get inventory storage data.

    @api {get} /cost-management/v1/reports/azure/storage/ Get inventory storage data
    @apiName getAzureStorageData
    @apiGroup Azure Report
    @apiVersion 1.0.0
    @apiDescription Get inventory data.

    @apiHeader {String} token User authorization token.

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParam (Query Param) {String} units The units used in the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope_value]=-10&order_by[cost]=asc&units=byte

    @apiSuccess {Object} group_by  The grouping to applied to the report.
    @apiSuccess {Object} filter  The filter to applied to the report.
    @apiSuccess {Object} data  The report data.
    @apiSuccess {Object} total Aggregates statistics for the report range.
    @apiSuccessExample {json} Success-Response:
        HTTP/1.1 200 OK
        {
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK

    """

    report = 'storage'
