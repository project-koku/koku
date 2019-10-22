
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
"""AWS views."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.serializers import QueryParamSerializer
from api.report.view import ReportView
from reporting.provider.aws.models import AWSTagsSummary


class AWSView(ReportView):
    """AWS Base View."""

    permission_classes = [AwsAccessPermission]
    provider = 'AWS'
    serializer = QueryParamSerializer
    query_handler = AWSReportQueryHandler
    tag_handler = [AWSTagsSummary]


class AWSCostView(AWSView):
    """Get cost data.

    @api {get} /cost-management/v1/reports/aws/costs/ Get cost data
    @apiName getAWSCostData
    @apiGroup AWS Report
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
            "group_by": {
                "account": [
                "*"
                ]
            },
            "order_by": {
                "cost": "asc"
            },
            "filter": {
                "resolution": "daily",
                "time_scope_value": -10,
                "time_scope_units": "day",
                "resource_scope": []
            },
            "data": [
                [
                {
                    "date": "2018-05-28",
                    "accounts": [
                        {
                            "account": "8577742690384",
                            "values": [
                                {
                                    "date": "2018-05-28",
                                    "units": "USD",
                                    "account": "8577742690384",
                                    "total": 1498.92962634
                                }
                            ]
                        },
                        {
                            "account": "9420673783214",
                            "values": [
                                {
                                    "date": "2018-05-28",
                                    "units": "USD",
                                    "account": "9420673783214",
                                    "total": 1065.845524241
                                }
                            ]
                        }
                    ]
                }
                ]
            ]
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        account,date,total,units
        6855812392331,2018-07,23008.281583543,USD
        3028898336671,2018-07,20826.675630200,USD
        7475489704610,2018-07,20305.483875161,USD
        2882243055256,2018-07,19474.534357638,USD
        6721340654404,2018-07,19356.197856632,USD

    """

    report = 'costs'


class AWSInstanceTypeView(AWSView):
    """Get inventory data.

    @api {get} /cost-management/v1/reports/aws/instance-types/ Get inventory instance type data
    @apiName getAWSInstanceTypeData
    @apiGroup AWS Report
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
            "group_by": {
                "account": [
                "*"
                ]
            },
            "filter": {
                "resolution": "daily",
                "time_scope_value": -10,
                "time_scope_units": "day",
                "resource_scope": []
            },
            "data": [
                [
                    {
                        "date": "2018-05-28",
                        "accounts": [
                            {
                                "account": 111111111111 ,
                                "instance_types": [
                                        {
                                            "instance_type": "t2.medium",
                                            "values": [
                                                {
                                                    "date": "2018-05-28",
                                                    "units": "Hrs",
                                                    "instance_type": "t2.medium",
                                                    "total": 5,
                                                    "count": 1
                                                }
                                            ]
                                        },
                                        {
                                            "instance_type": "m5.2xlarge",
                                            "values": [
                                                {
                                                    "date": "2018-05-28",
                                                    "units": "Hrs",
                                                    "instance_type": "m5.2xlarge",
                                                    "total": 29,
                                                    "count": 3
                                                }
                                            ]
                                        }
                                    ]
                            }
                        ]
                    },
                    {
                        "date": "2018-05-29",
                        "accounts": [
                            {
                                "account": 111111111111 ,
                                "instance_types": [
                                        {
                                            "instance_type": "m5.2xlarge",
                                            "values": [
                                                {
                                                    "date": "2018-05-28",
                                                    "units": "Hrs",
                                                    "instance_type": "m5.2xlarge",
                                                    "total": 29,
                                                    "count": 4
                                                }
                                            ]
                                        }
                                    ]
                            }
                        ]
                    }
                ]
            ],
            "total": {
                "value": 63,
                "units": "Hrs",
                "count": 5
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        account,date,instance_type,total,units
        3082416796941,2018-08-05,r4.large,11.0,Hrs
        0840549025238,2018-08-05,m5.large,11.0,Hrs
        0840549025238,2018-08-05,c5d.2xlarge,9.0,Hrs
        8133889256380,2018-08-05,c4.xlarge,8.0,Hrs
        3082416796941,2018-08-04,c5d.2xlarge,12.0,Hrs
        8133889256380,2018-08-04,c4.xlarge,12.0,Hrs
        2415722664993,2018-08-04,r4.large,10.0,Hrs
        8133889256380,2018-08-04,r4.large,10.0,Hrs

    """

    report = 'instance_type'


class AWSStorageView(AWSView):
    """Get inventory storage data.

    @api {get} /cost-management/v1/reports/aws/storage/ Get inventory storage data
    @apiName getAWSStorageData
    @apiGroup AWS Report
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
            "group_by": {
                "account": [
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
                    "date": "2018-08",
                    "accounts": [
                        {
                            "account": "0840549025238",
                            "values": [
                                {
                                    "date": "2018-08",
                                    "units": "GB-Mo",
                                    "account": "0840549025238",
                                    "total": 4066.923135971
                                }
                            ]
                        },
                        {
                            "account": "3082416796941",
                            "values": [
                                {
                                    "date": "2018-08",
                                    "units": "GB-Mo",
                                    "account": "3082416796941",
                                    "total": 3644.58070225345
                                }
                            ]
                        },
                        {
                            "account": "8133889256380",
                            "values": [
                                {
                                    "date": "2018-08",
                                    "units": "GB-Mo",
                                    "account": "8133889256380",
                                    "total": 3584.67567749966
                                }
                            ]
                        },
                        {
                            "account": "4783090375826",
                            "values": [
                                {
                                    "date": "2018-08",
                                    "units": "GB-Mo",
                                    "account": "4783090375826",
                                    "total": 3096.66740996526
                                }
                            ]
                        },
                        {
                            "account": "2415722664993",
                            "values": [
                                {
                                    "date": "2018-08",
                                    "units": "GB-Mo",
                                    "account": "2415722664993",
                                    "total": 2599.75765963921
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "value": 16992.6045853286,
                "units": "GB-Mo"
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        account,date,total,units
        0840549025238,2018-08,4066.923135971,GB-Mo
        3082416796941,2018-08,3644.58070225345,GB-Mo
        8133889256380,2018-08,3584.67567749966,GB-Mo
        4783090375826,2018-08,3096.66740996526,GB-Mo
        2415722664993,2018-08,2599.75765963921,GB-Mo

    """

    report = 'storage'
