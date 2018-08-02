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
import logging

from django.db.models import Value
from django.db.models.functions import Concat
from django.utils.translation import ugettext as _
from pint.errors import DimensionalityError, UndefinedUnitError
from querystring_parser import parser
from rest_framework import status
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.decorators import (api_view,
                                       authentication_classes,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.settings import api_settings

from api.iam.customer_manager import CustomerManager
from api.models import Customer
from api.report.queries import ReportQueryHandler
from api.report.serializers import QueryParamSerializer
from api.utils import UnitConverter

LOG = logging.getLogger(__name__)


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


def _convert_units(converter, data, to_unit):
    """Convert the units in a JSON structured report.

    Args:
        converter (api.utils.UnitConverter) Object doing unit conversion
        data (list,dict): The current block of the report being converted
        to_unit (str): The unit type to convert to

    Returns:
        (dict) The final return will be the unit converted report

    """
    suffix = None
    if isinstance(data, list):
        for entry in data:
            _convert_units(converter, entry, to_unit)
    elif isinstance(data, dict):
        for key in data:
            if key == 'total' and isinstance(data[key], dict):
                total = data[key]
                value = total.get('value')
                from_unit = total.get('units', '')
                if '-Mo' in from_unit:
                    from_unit, suffix = from_unit.split('-')
                new_value = converter.convert_quantity(value, from_unit, to_unit)
                total['value'] = new_value.magnitude
                new_unit = to_unit + '-' + suffix if suffix else to_unit
                total['units'] = new_unit
            elif key == 'total' and not isinstance(data[key], dict):
                total = data[key]
                from_unit = data.get('units', '')
                if '-Mo' in from_unit:
                    from_unit, suffix = from_unit.split('-')
                new_value = converter.convert_quantity(total, from_unit, to_unit)
                data['total'] = new_value.magnitude
                new_unit = to_unit + '-' + suffix if suffix else to_unit
                data['units'] = new_unit
            else:
                _convert_units(converter, data[key], to_unit)

    return data


def _generic_report(request, aggregate_key, units_key, **kwargs):
    """Generically query for reports.

    Args:
        request (Request): The HTTP request object
        aggregate_key (str): The report metric to be aggregated
            e.g. 'usage_amount' or 'unblended_cost'
        units_key (str): The field used to establish the reporting unit

    Returns:
        (Response): The report in a Response object

    """
    LOG.info(f'API: {request.path} USER: {request.user.username}')

    url_data = request.GET.urlencode()
    validation, params = process_query_parameters(url_data)
    if not validation:
        return Response(
            data=params,
            status=status.HTTP_400_BAD_REQUEST
        )

    tenant = get_tenant(request.user)
    handler = ReportQueryHandler(params,
                                 url_data,
                                 tenant,
                                 aggregate_key,
                                 units_key,
                                 **kwargs)
    output = handler.execute_query()

    if 'units' in params:
        try:
            to_unit = params['units']
            unit_converter = UnitConverter()
            output = _convert_units(unit_converter, output, to_unit)
        except (DimensionalityError, UndefinedUnitError):
            error = {'details': _('Unit conversion failed.')}
            raise ValidationError(error)

    LOG.debug(f'DATA: {output}')
    return Response(output)


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def costs(request):
    """Get cost data.

    @api {get} /api/v1/reports/costs/ Get cost data
    @apiName getCostData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get cost data.

    @apiHeader {String} token User authorization token.
    @apiHeader {String} accept HTTP Accept header. (See: RFC2616)
    @apiHeaderExample {json} Header-Example:
        {
            "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
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
        date,values.0.date,values.0.total,values.0.units
        2018-07-16,2018-07-16,0.800000000,USD
        2018-07-17,2018-07-17,0.768000000,USD
        2018-07-18,2018-07-18,0.800000000,USD
        2018-07-19,2018-07-19,0.768000000,USD
        2018-07-20,2018-07-20,0.448000000,USD

    """
    return _generic_report(request, 'unblended_cost', 'currency_code')


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def instance_type(request):
    """Get inventory data.

    @api {get} /api/v1/reports/inventory/instance-type/ Get inventory instance type data
    @apiName getInventoryInstanceTypeData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get inventory instance type data.

    @apiHeader {String} token User authorization token.
    @apiHeader {String} accept HTTP Accept header. (See: RFC2616)
    @apiHeaderExample {json} Header-Example:
        {
            "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
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
                    }
                ]
            ],
            "total": {
                "value": 34,
                "units": "Hrs",
                "count": 4
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        date,instance_types.0.instance_type,instance_types.0.values.0.count,instance_types.0.values.0.date,instance_types.0.values.0.instance_type,instance_types.0.values.0.total,instance_types.0.values.0.units,instance_types.1.instance_type,instance_types.1.values.0.count,instance_types.1.values.0.date,instance_types.1.values.0.instance_type,instance_types.1.values.0.total,instance_types.1.values.0.units
        2018-07-15,t2.micro,0,2018-07-15,t2.micro,39.0,,t2.small,0,2018-07-15,t2.small,25.0,Hrs
        2018-07-17,t2.micro,0,2018-07-17,t2.micro,25.0,,t2.small,0,2018-07-17,t2.small,24.0,Hrs
        2018-07-18,t2.micro,0,2018-07-18,t2.micro,25.0,,t2.small,0,2018-07-18,t2.small,25.0,Hrs
        2018-07-19,t2.micro,0,2018-07-19,t2.micro,25.0,,t2.small,0,2018-07-19,t2.small,24.0,Hrs

    """
    filter_scope = {'cost_entry_product__instance_type__isnull': False}
    annotations = {'instance_type':
                   Concat('cost_entry_product__instance_type', Value(''))}
    extras = {'filter': filter_scope,
              'annotations': annotations,
              'group_by': ['instance_type'],
              'count': 'resource_id'}
    return _generic_report(request,
                           'usage_amount',
                           'cost_entry_pricing__unit',
                           **extras)


@api_view(http_method_names=['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
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
            ],
            "total": {
                "value": 5475.922451027388,
                "units": "GB-Mo"
            }
        }
    @apiSuccessExample {text} Success-Response:
        HTTP/1.1 200 OK
        date,values.0.date,values.0.total,values.0.units
        2018-07-13,2018-07-13,1.6146062097,
        2018-07-14,2018-07-14,1.3458355445,
        2018-07-15,2018-07-15,1.7759989024,
        2018-07-16,2018-07-16,1.6147669752,

    """
    filter_scope = {'cost_entry_product__product_family': 'Storage'}
    extras = {'filter': filter_scope}
    return _generic_report(request,
                           'usage_amount',
                           'cost_entry_pricing__unit',
                           **extras)
