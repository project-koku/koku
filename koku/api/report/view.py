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
from django.utils.translation import ugettext as _
from querystring_parser import parser
from rest_framework import status
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.decorators import (api_view,
                                       authentication_classes,
                                       permission_classes)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from api.iam.customer_manager import CustomerManager
from api.models import Customer
from api.report.queries import ReportQueryHandler
from api.report.serializers import QueryParamSerializer


def process_query_parameters(url_data):
    """Process query parameters and raise any validation errors.

    Args:
        url_data    (String): the url string
    Returns:
        (Boolean): True if query params are valid, False otherwise
        (Dict): Dictionary parsed from query params string
    """
    output = None
    query_params = parser.parse(url_data)
    qps = QueryParamSerializer(data=query_params)
    validation = qps.is_valid()
    if not validation:
        output = qps.errors
    else:
        output = qps.data
    return (validation, output)


def get_tenant(user):
    """Get the tenant for the given user.

    Args:
        user    (DjangoUser): user to get the associated tenant
    Returns:
        (Tenant): Object used to get tenant specific data tables
    Raises:
        (ValidationError): If no tenant could be found for the user
    """
    tenant = None
    group = user.groups.first()
    if group:
        try:
            customer = Customer.objects.get(pk=group.id)
            manager = CustomerManager(customer.uuid)
            tenant = manager.get_tenant()
        except Customer.DoesNotExist:
            pass
    if tenant is None:
        error = {'details': _('Invalid user definition')}
        raise ValidationError(error)
    return tenant


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

    @apiHeader {String} token User authorization token.
    @apiHeaderExample {json} Header-Example:
        {
            "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
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
    """
    url_data = request.GET.urlencode()
    validation, value = process_query_parameters(url_data)
    if not validation:
        return Response(
            data=value,
            status=status.HTTP_400_BAD_REQUEST
        )
    tenant = get_tenant(request.user)
    handler = ReportQueryHandler(value,
                                 url_data,
                                 tenant,
                                 'unblended_cost',
                                 'currency_code')
    output = handler.execute_query()
    return Response(output)


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def instance_type(request):
    """Get inventory data.

    @api {get} /api/v1/reports/inventory/instance-type/ Get inventory instance type data
    @apiName getInventoryInstanceTypeData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get inventory instance type data.

    @apiHeader {String} token User authorization token.
    @apiHeaderExample {json} Header-Example:
        {
            "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
        }

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope_value]=-10&order_by[cost]=asc

    @apiSuccess {Object} group_by  The grouping to applied to the report.
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
                    "instance_types": [
                        {
                            "instance_type": "t2.medium",
                            "values": [
                                {
                                    "date": "2018-05-28",
                                    "units": "Hrs",
                                    "instance_type": "t2.medium",
                                    "total": 5
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
                                    "total": 29
                                }
                            ]
                        }
                    ]
                }
                ]
            ]
        }
    """
    url_data = request.GET.urlencode()
    validation, value = process_query_parameters(url_data)
    if not validation:
        return Response(
            data=value,
            status=status.HTTP_400_BAD_REQUEST
        )
    tenant = get_tenant(request.user)
    filter_scope = {'cost_entry_product__instance_type__isnull': False}
    annotations = {'instance_type':
                   Concat('cost_entry_product__instance_type', Value(''))}
    extras = {'filter': filter_scope,
              'annotations': annotations,
              'group_by': ['instance_type']}
    handler = ReportQueryHandler(value,
                                 url_data,
                                 tenant,
                                 'usage_amount',
                                 'cost_entry_pricing__unit',
                                 **extras)
    output = handler.execute_query()
    return Response(output)


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def storage(request):
    """Get inventory storage data.

    @api {get} /api/v1/reports/inventory/storage Get inventory storage data
    @apiName getInventoryStorageData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get inventory data.

    @apiHeader {String} token User authorization token.
    @apiHeaderExample {json} Header-Example:
        {
            "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
        }

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParam (Query Param) {Object} group_by The grouping to apply to the report.
    @apiParam (Query Param) {Object} order_by The ordering to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[resolution]=daily&filter[time_scope_value]=-10&order_by[cost]=asc

    @apiSuccess {Object} group_by  The grouping to applied to the report.
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
            "filter": {
                "resolution": "monthly",
                "time_scope_value": -1,
                "time_scope_units": "month",
                "resource_scope": []
            },
            "data": [
                [
                {
                    "date": "2018-07",
                    "accounts": [
                        {
                            "account": "4418636104713",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "4418636104713",
                                    "total": 1826.74238146924
                                }
                            ]
                        },
                        {
                            "account": "8577742690384",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "8577742690384",
                                    "total": 1137.74036198065
                                }
                            ]
                        },
                        {
                            "account": "3474227945050",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "3474227945050",
                                    "total": 1045.80659412797
                                }
                            ]
                        },
                        {
                            "account": "7249815104968",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "7249815104968",
                                    "total": 807.326470618818
                                }
                            ]
                        },
                        {
                            "account": "9420673783214",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "9420673783214",
                                    "total": 658.306642830709
                                }
                            ]
                        }
                    ]
                }
                ]
            ]
        }
    """
    url_data = request.GET.urlencode()
    validation, value = process_query_parameters(url_data)
    if not validation:
        return Response(
            data=value,
            status=status.HTTP_400_BAD_REQUEST
        )
    tenant = get_tenant(request.user)
    filter_scope = {'cost_entry_product__product_family': 'Storage'}
    extras = {'filter': filter_scope}
    handler = ReportQueryHandler(value,
                                 url_data,
                                 tenant,
                                 'usage_amount',
                                 'cost_entry_pricing__unit',
                                 **extras)
    output = handler.execute_query()
    return Response(output)
