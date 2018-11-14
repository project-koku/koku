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

from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPQueryParamSerializer
from api.report.view import _generic_report


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def memory(request):
    """Get OCP memory usage data.

    @api {get} /api/v1/reports/ocp/memory Get memory usage data
    @apiName getInventoryStorageData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get OCP memory usage data.

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
        HTTP/1.1 200 OK
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
                    "date": "2018-10",
                    "projects": [
                        {
                            "project": "default",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "default",
                                    "memory_usage_gigabytes": 0.162249,
                                    "memory_requests_gigabytes": 1.063302
                                }
                            ]
                        },
                        {
                            "project": "metering",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "metering",
                                    "memory_usage_gigabytes": 5.899788,
                                    "memory_requests_gigabytes": 7.007081
                                }
                            ]
                        },
                        {
                            "project": "monitoring",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "monitoring",
                                    "memory_usage_gigabytes": 3.178287,
                                    "memory_requests_gigabytes": 4.153526
                                }
                            ]
                        },
                        {
                            "project": "openshift-web-console",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "openshift-web-console",
                                    "memory_usage_gigabytes": 0.068988,
                                    "memory_requests_gigabytes": 0.207677
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "pod_usage_memory_gigabytes": 9.309312,
                "pod_request_memory_gigabytes": 12.431585
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cpu_limit,cpu_requests_core_hours,cpu_usage_core_hours,date,project
        ,9.506666,0.119385,2018-10,default
        ,53.985832,4.464511,2018-10,metering
        ,17.920067,7.861343,2018-10,monitoring
        ,4.753333,0.862687,2018-10,openshift-web-console

    """
    extras = {'report_type': 'mem'}
    return _generic_report(request, OCPQueryParamSerializer, OCPReportQueryHandler, **extras)


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def cpu(request):
    """Get OCP cpu usage data.

    @api {get} /api/v1/reports/ocp/cpu Get cpu usage data
    @apiName getInventoryStorageData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get OCP cpu usage data.

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
        HTTP/1.1 200 OK
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
                    "date": "2018-10",
                    "projects": [
                        {
                            "project": "default",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "default",
                                    "cpu_limit": null,
                                    "cpu_usage_core_hours": 0.119385,
                                    "cpu_requests_core_hours": 9.506666
                                }
                            ]
                        },
                        {
                            "project": "metering",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "metering",
                                    "cpu_limit": null,
                                    "cpu_usage_core_hours": 4.464511,
                                    "cpu_requests_core_hours": 53.985832
                                }
                            ]
                        },
                        {
                            "project": "monitoring",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "monitoring",
                                    "cpu_limit": null,
                                    "cpu_usage_core_hours": 7.861343,
                                    "cpu_requests_core_hours": 17.920067
                                }
                            ]
                        },
                        {
                            "project": "openshift-web-console",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "openshift-web-console",
                                    "cpu_limit": null,
                                    "cpu_usage_core_hours": 0.862687,
                                    "cpu_requests_core_hours": 4.753333
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "pod_usage_cpu_core_hours": 13.307928,
                "pod_request_cpu_core_hours": 86.165898
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cpu_limit,cpu_requests_core_hours,cpu_usage_core_hours,date,project
        ,9.506666,0.119385,2018-10,default
        ,53.985832,4.464511,2018-10,metering
        ,17.920067,7.861343,2018-10,monitoring
        ,4.753333,0.862687,2018-10,openshift-web-console

    """
    extras = {'report_type': 'cpu'}
@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def charges(request):
    """Get OCP cpu usage data.

    @api {get} /api/v1/reports/charge/ocp/ Get OCP charge data
    @apiName getOCPChargeData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get OCP charge data.

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
                    "date": "2018-11",
                    "projects": [
                        {
                            "project": "monitoring",
                            "values": [
                                {
                                    "date": "2018-11",
                                    "project": "monitoring",
                                    "charge": 3.2
                                }
                            ]
                        },
                        {
                            "project": "metering-hccm",
                            "values": [
                                {
                                    "date": "2018-11",
                                    "project": "metering-hccm",
                                    "charge": 3.0
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "charge": 6.2
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        charge,date,project
        3.200000,2018-11,monitoring
        3.000000,2018-11,metering-hccm

    """
    extras = {'report_type': 'charge'}
    return _generic_report(request, OCPChargeQueryParamSerializer,
                           OCPReportQueryHandler, **extras)
