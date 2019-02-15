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

"""View for OCP on AWS Usage Reports."""

from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.settings import api_settings

from api.report.view import _generic_report


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def costs(request):
    """Get OCP on AWS cost usage data.

    @api {get} /api/v1/reports/costs/ocp/ Get memory usage data
    @apiName getOCPCostData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get OCP cost data.

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
    return _generic_report(request, report='costs', provider='ocp_aws')


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
    return _generic_report(request, report='storage', provider='ocp_aws')


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def instance_type(request):
    """Get OCP on AWS storage usage data.

    @api {get} /api/v1/reports/inventory/ocp/instance-type Get inventory instance data
    @apiName getOCPAWSInventoryInstanceData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get OCP on AWS instance usage data.

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
    return _generic_report(request, report='instance_type', provider='ocp_aws')
