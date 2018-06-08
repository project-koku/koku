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
import copy

from querystring_parser import parser
from rest_framework import status
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.decorators import (api_view,
                                       authentication_classes,
                                       permission_classes)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.report.serializers import QueryParamSerializer


def process_query_parameters(url_data):
    """Process query parameters and raise any validation errors."""
    query_params = parser.parse(url_data)
    qps = QueryParamSerializer(data=query_params)
    if not qps.is_valid():
        return Response(
            data=qps.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    query_data = copy.deepcopy(qps.data)
    return query_data


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def costs(request):
    """Get cost data.

    @api {get} /api/v1/reports/costs/ Get cost data
    @apiName getCostData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get cost data.

    @apiHeader {String} token User authorizaton token.
    @apiHeaderExample {json} Header-Example:
        {
            "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
        }

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope]=-10&order_by[cost]=asc

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
                "time_scope": -10,
                "resource_scope": []
            },
            "data": [
                [
                {
                    "2018-05-28": [
                    {
                        "accountA": 52.8,
                        "accountB": 29.47,
                        "accountC": 1.39
                    }
                    ]
                }
                ]
            ]
        }
    """
    output = process_query_parameters(request.GET.urlencode())
    output['data'] = []
    return Response(output)


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def inventory(request):
    """Get inventory data.

    @api {get} /api/v1/reports/inventory/ Get cost data
    @apiName getInventoryData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get inventory data.

    @apiHeader {String} token User authorizaton token.
    @apiHeaderExample {json} Header-Example:
        {
            "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
        }

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope]=-10&order_by[cost]=asc

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
                "time_scope": -10,
                "resource_scope": []
            },
            "data": [
                [
                {
                    "2018-05-28": [
                    {
                        "t2.medium": 5,
                        "m5.2xlarge": 290
                    }
                    ]
                }
                ]
            ]
        }
    """
    output = process_query_parameters(request.GET.urlencode())
    output['data'] = []
    return Response(output)
