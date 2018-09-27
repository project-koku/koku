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
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.settings import api_settings

from api.models import Tenant, User
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
    if user:
        try:
            customer = user.customer
            tenant = Tenant.objects.get(schema_name=customer.schema_name)
        except User.DoesNotExist:
            pass
    if tenant is None:
        error = {'details': _('Invalid user definition')}
        raise ValidationError(error)
    return tenant


def _find_unit():
    """Find the original unit for a report dataset."""
    unit = None

    def __unit_finder(data):
        nonlocal unit
        if isinstance(data, list):
            for entry in data:
                __unit_finder(entry)
        elif isinstance(data, dict):
            for key in data:
                if key == 'units' and data[key] and unit is None:
                    unit = data[key]
                else:
                    __unit_finder(data[key])
        return unit

    return __unit_finder


def _fill_in_missing_units(unit):
    """Fill in missing unit information."""
    def __unit_filler(data):
        if isinstance(data, list):
            for entry in data:
                __unit_filler(entry)
        elif isinstance(data, dict):
            for key in data:
                if key == 'units':
                    if not data[key]:
                        data[key] = unit
                else:
                    __unit_filler(data[key])
        return data
    return __unit_filler


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
    if kwargs:
        kwargs['accept_type'] = request.META.get('HTTP_ACCEPT')
    else:
        kwargs = {'accept_type': request.META.get('HTTP_ACCEPT')}

    handler = ReportQueryHandler(params,
                                 url_data,
                                 tenant,
                                 aggregate_key,
                                 units_key,
                                 **kwargs)
    output = handler.execute_query()

    if 'units' in params:
        from_unit = _find_unit()(output['data'])
        if from_unit:
            try:
                to_unit = params['units']
                unit_converter = UnitConverter()
                output = _fill_in_missing_units(from_unit)(output)
                output = _convert_units(unit_converter, output, to_unit)
            except (DimensionalityError, UndefinedUnitError):
                error = {'details': _('Unit conversion failed.')}
                raise ValidationError(error)

    LOG.debug(f'DATA: {output}')
    return Response(output)


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
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
    extras = {'report_type': 'costs'}
    return _generic_report(request, 'unblended_cost', 'currency_code', **extras)


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
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
    annotations = {'instance_type':
                   Concat('cost_entry_product__instance_type', Value(''))}
    extras = {'annotations': annotations,
              'group_by': ['instance_type'],
              'count': 'resource_id',
              'report_type': 'instance_type'}
    return _generic_report(request,
                           'usage_amount',
                           'cost_entry_pricing__unit',
                           **extras)


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def storage(request):
    """Get inventory storage data.

    @api {get} /api/v1/reports/inventory/storage Get inventory storage data
    @apiName getInventoryStorageData
    @apiGroup Report
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
    extras = {'report_type': 'storage'}
    return _generic_report(request,
                           'usage_amount',
                           'cost_entry_pricing__unit',
                           **extras)
