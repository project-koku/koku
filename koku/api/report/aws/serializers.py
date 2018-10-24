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
"""Report Serializers."""
from pint.errors import UndefinedUnitError
from rest_framework import serializers

from api.report.serializers import (StringOrListField, handle_invalid_fields, validate_field)
from api.utils import UnitConverter


class GroupBySerializer(serializers.Serializer):
    """Serializer for handling query parameter group_by."""

    account = StringOrListField(child=serializers.CharField(),
                                required=False)
    avail_zone = StringOrListField(child=serializers.CharField(),
                                   required=False)
    instance_type = StringOrListField(child=serializers.CharField(),
                                      required=False)
    region = StringOrListField(child=serializers.CharField(),
                               required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)
    storage_type = StringOrListField(child=serializers.CharField(),
                                     required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid
        """
        handle_invalid_fields(self, data)
        return data


class OrderBySerializer(serializers.Serializer):
    """Serializer for handling query parameter order_by."""

    ORDER_CHOICES = (('asc', 'asc'), ('desc', 'desc'))
    total = serializers.ChoiceField(choices=ORDER_CHOICES,
                                    required=False)
    delta = serializers.ChoiceField(choices=ORDER_CHOICES,
                                    required=False)
    inventory = serializers.ChoiceField(choices=ORDER_CHOICES,
                                        required=False)
    account_alias = serializers.ChoiceField(choices=ORDER_CHOICES,
                                            required=False)
    region = serializers.ChoiceField(choices=ORDER_CHOICES,
                                     required=False)
    service = serializers.ChoiceField(choices=ORDER_CHOICES,
                                      required=False)

    def validate(self, data):
        """Validate incoming data."""
        handle_invalid_fields(self, data)
        return data


class FilterSerializer(serializers.Serializer):
    """Serializer for handling query parameter filter."""

    RESOLUTION_CHOICES = (
        ('daily', 'daily'),
        ('monthly', 'monthly'),
    )
    TIME_CHOICES = (
        ('-10', '-10'),
        ('-30', '-30'),
        ('-1', '1'),
        ('-2', '-2'),
    )
    TIME_UNIT_CHOICES = (
        ('day', 'day'),
        ('month', 'month'),
    )

    resolution = serializers.ChoiceField(choices=RESOLUTION_CHOICES,
                                         required=False)
    time_scope_value = serializers.ChoiceField(choices=TIME_CHOICES,
                                               required=False)
    time_scope_units = serializers.ChoiceField(choices=TIME_UNIT_CHOICES,
                                               required=False)
    resource_scope = StringOrListField(child=serializers.CharField(),
                                       required=False)
    limit = serializers.IntegerField(required=False, min_value=1)
    account = StringOrListField(child=serializers.CharField(),
                                required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)
    region = StringOrListField(child=serializers.CharField(),
                               required=False)
    avail_zone = StringOrListField(child=serializers.CharField(),
                                   required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid
        """
        handle_invalid_fields(self, data)

        resolution = data.get('resolution')
        time_scope_value = data.get('time_scope_value')
        time_scope_units = data.get('time_scope_units')

        if time_scope_units and time_scope_value:
            msg = 'Valid values are {} when time_scope_units is {}'
            if (time_scope_units == 'day' and (time_scope_value == '-1' or time_scope_value == '-2')):
                valid_values = ['-10', '-30']
                valid_vals = ', '.join(valid_values)
                error = {'time_scope_value': msg.format(valid_vals, 'day')}
                raise serializers.ValidationError(error)
            if (time_scope_units == 'day' and resolution == 'monthly'):
                valid_values = ['daily']
                valid_vals = ', '.join(valid_values)
                error = {'resolution': msg.format(valid_vals, 'day')}
                raise serializers.ValidationError(error)
            if (time_scope_units == 'month' and (time_scope_value == '-10' or time_scope_value == '-30')):
                valid_values = ['-1', '-2']
                valid_vals = ', '.join(valid_values)
                error = {'time_scope_value': msg.format(valid_vals, 'month')}
                raise serializers.ValidationError(error)
        return data


class QueryParamSerializer(serializers.Serializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    OPERATION_CHOICES = (
        ('sum', 'sum'),
        ('none', 'none'),
    )

    delta = serializers.BooleanField(required=False)
    group_by = GroupBySerializer(required=False)
    order_by = OrderBySerializer(required=False)
    filter = FilterSerializer(required=False)
    units = serializers.CharField(required=False)
    operation = serializers.ChoiceField(choices=OPERATION_CHOICES,
                                        required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid
        """
        handle_invalid_fields(self, data)
        return data

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid
        """
        validate_field(self, 'group_by', GroupBySerializer, value)
        return value

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid
        """
        validate_field(self, 'order_by', OrderBySerializer, value)
        return value

    def validate_filter(self, value):
        """Validate incoming filter data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter field inputs are invalid
        """
        validate_field(self, 'filter', FilterSerializer, value)
        return value

    def validate_units(self, value):
        """Validate incoming units data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if units field inputs are invalid

        """
        unit_converter = UnitConverter()
        try:
            unit_converter.validate_unit(value)
        except (AttributeError, UndefinedUnitError):
            error = {'units': f'{value} is not a supported unit'}
            raise serializers.ValidationError(error)

        return value
