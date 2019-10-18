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

"""View for OpenShift Usage Reports."""

from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import (OCPCostQueryParamSerializer,
                                        OCPInventoryQueryParamSerializer)
from api.report.view import ReportView
from reporting.provider.ocp.models import (OCPStorageVolumeClaimLabelSummary,
                                           OCPStorageVolumeLabelSummary,
                                           OCPUsagePodLabelSummary)


class OCPView(ReportView):
    """OCP Base View."""

    permission_classes = [OpenShiftAccessPermission]
    provider = 'OCP'
    serializer = OCPInventoryQueryParamSerializer
    query_handler = OCPReportQueryHandler
    tag_handler = [OCPUsagePodLabelSummary,
                   OCPStorageVolumeClaimLabelSummary,
                   OCPStorageVolumeLabelSummary]


class OCPMemoryView(OCPView):
    """Get OpenShift memory usage data.

    @api {get} /cost-management/v1/reports/openshift/memory/ Get memory usage data
    @apiName getOpenshiftMemoryData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift memory usage data.

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

    report = 'memory'


class OCPCpuView(OCPView):
    """Get OpenShift compute usage data.

    @api {get} /cost-management/v1/reports/openshift/compute/ Get compute usage data
    @apiName getOpenShiftInventoryCPUData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift compute usage data.

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

    report = 'cpu'


class OCPCostView(OCPView):
    """Get OpenShift cost data.

    @api {get} /cost-management/v1/reports/openshift/costs/ Get OpenShift costs data
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
    @apiSuccessExample {json} Success-Response:
        HTTP 200 OK
        {
            "meta": {
                "count": 1,
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
                "total": {
                    "infrastructure_cost": {
                        "value": 1960.75,
                        "units": "USD"
                    },
                    "derived_cost": {
                        "value": 0.0,
                        "units": "USD"
                    },
                    "cost": {
                        "value": 1960.75,
                        "units": "USD"
                    }
                }
            },
            "links": {
                "first": "/cost-management/v1/reports/openshift/costs/?filter%5Bresolution%5D=monthly&filter%5Btime_scope_units%5D=month&filter%5Btime_scope_value%5D=-1&group_by%5Bproject%5D=%2A&limit=100&offset=0",  # noqa: E501
                "next": null,
                "previous": null,
                "last": "/local/v1/reports/openshift/costs/?filter%5Bresolution%5D=monthly&filter%5Btime_scope_units%5D=month&filter%5Btime_scope_value%5D=-1&group_by%5Bproject%5D=%2A&limit=100&offset=0"  # noqa: E501
            },
            "data": [
                {
                    "date": "2019-03",
                    "projects": [
                        {
                            "project": "namespace_ci",
                            "values": [
                                {
                                    "date": "2019-03",
                                    "project": "namespace_ci",
                                    "infrastructure_cost": {
                                        "value": 1960.75,
                                        "units": "USD"
                                    },
                                    "derived_cost": {
                                        "value": 0.0,
                                        "units": "USD"
                                    },
                                    "cost": {
                                        "value": 1960.75,
                                        "units": "USD"
                                    }
                                }
                            ]
                        },
                        {
                            "project": "namespace_qe",
                            "values": [
                                {
                                    "date": "2019-03",
                                    "project": "namespace_qw",
                                    "infrastructure_cost": {
                                        "value": 0.0,
                                        "units": "USD"
                                    },
                                    "derived_cost": {
                                        "value": 0.0,
                                        "units": "USD"
                                    },
                                    "cost": {
                                        "value": 0.0,
                                        "units": "USD"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        cost,cost_units,date,derived_cost,infrastructure_cost,project
        1960.750000,USD,2019-03,0.000000,1960.750000,namespace_ci
        0.000000,USD,2019-03,0.000000,0,namespace_hyper

    """

    report = 'costs'
    serializer = OCPCostQueryParamSerializer


class OCPVolumeView(OCPView):
    """Get OpenShift volume usage data.

    @api {get} /cost-management/v1/reports/openshift/volume/ Get volume usage data
    @apiName getOpenShiftVolumeData
    @apiGroup OpenShift Report
    @apiVersion 1.0.0
    @apiDescription Get OpenShift volume usage data.

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
                "time_scope_value": "-1"
            },
            "data": [
                {
                    "date": "2019-02",
                    "projects": [
                        {
                            "project": "metering-hccm",
                            "values": [
                                {
                                    "date": "2019-02",
                                    "project": "metering-hccm",
                                    "usage": 283.455815,
                                    "request": 14058.333334,
                                    "capacity": 13732.252982,
                                    "charge": null,
                                    "units": "GB-Mo"
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "usage": 283.455815,
                "request": 14058.333334,
                "capacity": 13732.252982,
                "charge": null,
                "units": "GB-Mo"
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        capacity,charge,date,project,request,units,usage
        13732.252982,,2019-02,metering-hccm,14058.333334,GB-Mo,283.455815

    """

    report = 'volume'
