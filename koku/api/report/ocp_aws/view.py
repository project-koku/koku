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

"""View for OpenShift on AWS Usage Reports."""

from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.report.ocp_aws.query_handler import OCPAWSReportQueryHandler
from api.report.ocp_aws.serializers import OCPAWSQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.aws.models import AWSTagsSummary


class OCPAWSView(ReportView):
    """OCP+AWS Base View."""

    permission_classes = [AwsAccessPermission, OpenShiftAccessPermission]
    provider = 'OCP_AWS'
    serializer = OCPAWSQueryParamSerializer
    query_handler = OCPAWSReportQueryHandler
    tag_handler = [AWSTagsSummary]


class OCPAWSCostView(OCPAWSView):
    """Get OpenShift on AWS cost usage data.

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


class OCPAWSStorageView(OCPAWSView):
    """Get OpenShift on AWS storage usage data.

    @api {get} /cost-management/v1/reports/openshift/infrastructures/aws/storage/ Get OpenShift on AWS storage usage.
    @apiName getOpenShiftAWSStorageData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift on AWS storage usage data.

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
            "group_by": {
                "project": [
                    "*"
                ]
            },
            "filter": {
                "resolution": "monthly",
                "time_scope_value": "-1",
                "time_scope_units": "month"
            },
            "data": [
                {
                    "date": "2019-01",
                    "projects": [
                        {
                            "project": "namespace_ci",
                            "values": [
                                {
                                    "date": "2019-01",
                                    "units": "GB-Mo",
                                    "project": "namespace_ci",
                                    "cost": 11.674377,
                                    "total": 24.0
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "units": "GB-Mo",
                "cost": 11.674377,
                "total": 24.0
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cost,date,project,total,units
        11.674377,2019-01,namespace_ci,24.0,GB-Mo

    """

    report = 'storage'


class OCPAWSInstanceTypeView(OCPAWSView):
    """Get OpenShift on AWS instance usage data.

    @api {get} /cost-management/v1/reports/openshift/infrastructures/aws/instance-types/ Get instance data
    @apiName getOpenShiftAWSInventoryInstanceData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift on AWS instance usage data.

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
            "group_by": {
                "project": [
                    "*"
                ]
            },
            "filter": {
                "resolution": "monthly",
                "time_scope_value": "-2",
                "time_scope_units": "month"
            },
            "data": [
                {
                    "date": "2019-01",
                    "projects": [
                        {
                            "project": "namespace_ci",
                            "instance_types": [
                                {
                                    "instance_type": "m5.large",
                                    "values": [
                                        {
                                            "instance_type": "m5.large",
                                            "date": "2019-01",
                                            "units": "Hrs",
                                            "project": "namespace_ci",
                                            "cost": 915.889752,
                                            "count": 1,
                                            "total": 120.0
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "project": "namespace_qa",
                            "instance_types": [
                                {
                                    "instance_type": "m5.large",
                                    "values": [
                                        {
                                            "instance_type": "m5.large",
                                            "date": "2019-01",
                                            "units": "Hrs",
                                            "project": "namespace_qa",
                                            "cost": 939.377001,
                                            "count": 1,
                                            "total": 140.0
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "units": "Hrs",
                "cost": 1855.266753,
                "count": 2,
                "value": 260.0
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cost,count,date,instance_type,project,total,units
        915.889752,1,2019-01,m5.large,namespace_ci,1488.0,Hrs
        939.377001,1,2019-01,m5.large,namespace_qa,1488.0,Hrs

    """

    report = 'instance_type'
