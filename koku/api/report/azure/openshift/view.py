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

"""View for OpenShift on Azure Usage Reports."""

from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.openshift.serializers import OCPAzureQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.azure.models import AzureTagsSummary


class OCPAzureView(ReportView):
    """OCP+Azure Base View."""

    permission_classes = [AzureAccessPermission, OpenShiftAccessPermission]
    provider = 'OCP_Azure'
    serializer = OCPAzureQueryParamSerializer
    query_handler = OCPAzureReportQueryHandler
    tag_handler = [AzureTagsSummary]


class OCPAzureCostView(OCPAzureView):
    """Get OpenShift on Azure cost usage data.

    @api {get} /cost-management/v1/reports/openshift/costs/ Get OpenShift cost data
    @apiName getOpenShiftCostData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift cost data.

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

    """

    report = 'costs'


class OCPAzureInstanceTypeView(OCPAzureView):
    """Get OpenShift on Azure instance usage data.

    @api {get} /cost-management/v1/reports/openshift/infrastructures/azure/instance-types/ Get instance data
    @apiName getOpenShiftAzureInventoryInstanceData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift on Azure instance usage data.

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
        HTTP 200 OK
        Allow: OPTIONS, GET
        Content-Type: application/json
        Vary: Accept

        {
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cost,count,date,instance_type,project,total,units
        915.889752,1,2019-01,m5.large,namespace_ci,1488.0,Hrs
        939.377001,1,2019-01,m5.large,namespace_qa,1488.0,Hrs

    """

    report = 'instance_type'


class OCPAzureStorageView(OCPAzureView):
    """Get OpenShift on Azure storage usage data.

    @api {get} /cost-management/v1/reports/openshift/infrastructures/azure/storage/ Get OpenShift on Azure storage usage.  # noqa: E501
    @apiName getOpenShiftAzureStorageData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift on Azure storage usage data.

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
        HTTP 200 OK
        Allow: GET, OPTIONS
        Content-Type: application/json
        Vary: Accept

        {
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cost,date,project,total,units
        11.674377,2019-01,namespace_ci,24.0,GB-Mo

    """

    report = 'storage'
