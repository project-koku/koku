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
from django.views.decorators.vary import vary_on_headers
from pint.errors import DimensionalityError, UndefinedUnitError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common import RH_IDENTITY_HEADER
from api.common.pagination import ReportPagination, ReportRankedPagination
from api.query_params import QueryParameters
from api.utils import UnitConverter

LOG = logging.getLogger(__name__)


def get_paginator(filter_query_params, count):
    """Determine which paginator to use based on query params."""
    if 'offset' in filter_query_params:
        paginator = ReportRankedPagination()
        paginator.count = count
    else:
        paginator = ReportPagination()
    return paginator


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


class ReportView(APIView):
    """
    A shared view for all koku reports.

    This view maps the serializer based on self.provider and self.report.
    It providers one GET endpoint for the reports.
    """

    @vary_on_headers(RH_IDENTITY_HEADER)
    def get(self, request):
        """Get Report Data.

        This method is responsible for passing request data to the reporting APIs.

        Args:
            request (Request): The HTTP request object

        Returns:
            (Response): The report in a Response object

        """
        LOG.debug(f'API: {request.path} USER: {request.user.username}')

        try:
            params = QueryParameters(request=request,
                                     caller=self)
        except ValidationError as exc:
            return Response(data=exc.detail, status=status.HTTP_400_BAD_REQUEST)

        handler = self.query_handler(params)
        output = handler.execute_query()
        max_rank = handler.max_rank

        if 'units' in params.parameters:
            from_unit = _find_unit()(output['data'])
            if from_unit:
                try:
                    to_unit = params.parameters.get('units')
                    unit_converter = UnitConverter()
                    output = _fill_in_missing_units(from_unit)(output)
                    output = _convert_units(unit_converter, output, to_unit)
                except (DimensionalityError, UndefinedUnitError):
                    error = {'details': _('Unit conversion failed.')}
                    raise ValidationError(error)

        paginator = get_paginator(params.parameters.get('filter', {}), max_rank)
        paginated_result = paginator.paginate_queryset(output, request)
        LOG.debug(f'DATA: {output}')
        return paginator.get_paginated_response(paginated_result)
