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

from django.utils.translation import ugettext as _
from pint.errors import DimensionalityError, UndefinedUnitError
from querystring_parser import parser
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from api.models import Tenant, User
from api.utils import UnitConverter

LOG = logging.getLogger(__name__)


def process_query_parameters(url_data, provider_serializer):
    """Process query parameters and raise any validation errors.

    Args:
        url_data    (String): the url string
    Returns:
        (Boolean): True if query params are valid, False otherwise
        (Dict): Dictionary parsed from query params string
    """
    output = None
    query_params = parser.parse(url_data)
    qps = provider_serializer(data=query_params)
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


def _generic_report(request, provider_parameter_serializer, provider_query_hdlr, **kwargs):
    """Generically query for reports.

    Args:
        request (Request): The HTTP request object

    Returns:
        (Response): The report in a Response object

    """
    LOG.info(f'API: {request.path} USER: {request.user.username}')

    url_data = request.GET.urlencode()
    validation, params = process_query_parameters(url_data, provider_parameter_serializer)
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

    handler = provider_query_hdlr(params,
                                  url_data,
                                  tenant,
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
