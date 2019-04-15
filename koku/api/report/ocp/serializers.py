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
"""OCP Report Serializers."""
from django.utils.translation import ugettext as _
from pint.errors import UndefinedUnitError
from rest_framework import serializers

from api.report.serializers import (StringOrListField,
                                    add_operator_specified_fields,
                                    handle_invalid_fields,
                                    validate_field)
from api.utils import UnitConverter

OP_FIELDS = ('project', 'cluster', 'node')


class GroupBySerializer(serializers.Serializer):
    """Serializer for handling query parameter group_by."""

    cluster = StringOrListField(child=serializers.CharField(),
                                required=False)
    project = StringOrListField(child=serializers.CharField(),
                                required=False)
    node = StringOrListField(child=serializers.CharField(),
                             required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the GroupBySerializer."""
        tag_keys = kwargs.pop('tag_keys', None)

        super().__init__(*args, **kwargs)

        if tag_keys is not None:
            tag_keys = {key: StringOrListField(child=serializers.CharField(),
                                               required=False)
                        for key in tag_keys}
            # Add OCP tag keys to allowable fields
            self.fields.update(tag_keys)
        add_operator_specified_fields(self.fields, OP_FIELDS)

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

    cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                   required=False)
    infrastructure_cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                                  required=False)
    derived_cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                           required=False)
    cluster = serializers.ChoiceField(choices=ORDER_CHOICES,
                                      required=False)
    project = serializers.ChoiceField(choices=ORDER_CHOICES,
                                      required=False)
    node = serializers.ChoiceField(choices=ORDER_CHOICES,
                                   required=False)
    delta = serializers.ChoiceField(choices=ORDER_CHOICES,
                                    required=False)

    def validate(self, data):
        """Validate incoming data."""
        handle_invalid_fields(self, data)
        return data


class InventoryOrderBySerializer(OrderBySerializer):
    """Order By Serializer for CPU and Memory endpoints."""

    usage = serializers.ChoiceField(choices=OrderBySerializer.ORDER_CHOICES,
                                    required=False)
    request = serializers.ChoiceField(choices=OrderBySerializer.ORDER_CHOICES,
                                      required=False)
    limit = serializers.ChoiceField(choices=OrderBySerializer.ORDER_CHOICES,
                                    required=False)


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

    INFRASTRUCTURE_CHOICES = (
        ('aws', 'aws'),
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
    offset = serializers.IntegerField(required=False, min_value=0)
    project = StringOrListField(child=serializers.CharField(),
                                required=False)
    cluster = StringOrListField(child=serializers.CharField(),
                                required=False)
    pod = StringOrListField(child=serializers.CharField(),
                            required=False)
    node = StringOrListField(child=serializers.CharField(),
                             required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES,
                                              required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the FilterSerializer."""
        tag_keys = kwargs.pop('tag_keys', None)

        super().__init__(*args, **kwargs)

        if tag_keys is not None:
            tag_keys = {key: StringOrListField(child=serializers.CharField(),
                                               required=False)
                        for key in tag_keys}
            # Add OCP tag keys to allowable fields
            self.fields.update(tag_keys)
        add_operator_specified_fields(self.fields, OP_FIELDS)

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

        if data.get('infrastructures'):
            infra_value = data['infrastructures']
            data['infrastructures'] = [infra_value.upper()]

        if time_scope_units and time_scope_value:
            msg = 'Valid values are {} when time_scope_units is {}'
            if (time_scope_units == 'day' and  # noqa: W504
                (time_scope_value == '-1' or time_scope_value == '-2')):
                valid_values = ['-10', '-30']
                valid_vals = ', '.join(valid_values)
                error = {'time_scope_value': msg.format(valid_vals, 'day')}
                raise serializers.ValidationError(error)
            if (time_scope_units == 'day' and resolution == 'monthly'):
                valid_values = ['daily']
                valid_vals = ', '.join(valid_values)
                error = {'resolution': msg.format(valid_vals, 'day')}
                raise serializers.ValidationError(error)
            if (time_scope_units == 'month' and  # noqa: W504
                    (time_scope_value == '-10' or time_scope_value == '-30')):
                valid_values = ['-1', '-2']
                valid_vals = ', '.join(valid_values)
                error = {'time_scope_value': msg.format(valid_vals, 'month')}
                raise serializers.ValidationError(error)
        return data


class OCPQueryParamSerializer(serializers.Serializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    group_by = GroupBySerializer(required=False)
    units = serializers.CharField(required=False)

    # Adding pagination fields to the serializer because we validate
    # before running reports and paginating
    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        # Grab tag keys to pass to filter serializer
        self.tag_keys = kwargs.pop('tag_keys', None)
        super().__init__(*args, **kwargs)

        tag_fields = {
            'filter': FilterSerializer(required=False, tag_keys=self.tag_keys),
            'group_by': GroupBySerializer(required=False, tag_keys=self.tag_keys)
        }

        self.fields.update(tag_fields)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid
        """
        error = {}
        if 'delta' in data.get('order_by', {}) and 'delta' not in data:
            error['order_by'] = _('Cannot order by delta without a delta param')
            raise serializers.ValidationError(error)

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
        validate_field(self, 'group_by', GroupBySerializer, value,
                       tag_keys=self.tag_keys)
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
        validate_field(self, 'filter', FilterSerializer, value,
                       tag_keys=self.tag_keys)
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


class OCPInventoryQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling inventory query parameters."""

    delta_choices = (
        'cost',
        'usage',
        'request',
    )

    curren_month_delta_fields = (
        'usage',
        'request',
        'limit',
        'capacity'
    )

    delta = serializers.CharField(required=False)
    order_by = InventoryOrderBySerializer(required=False)

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid
        """
        validate_field(self, 'order_by', InventoryOrderBySerializer, value)
        return value

    def validate_delta(self, value):
        """Validate delta is valid."""
        error = {}
        if '__' in value:
            values = value.split('__')
            if len(values) != 2:
                error[value] = _('Only two fields may be compared')
                raise serializers.ValidationError(error)
            for val in values:
                if val not in self.curren_month_delta_fields:
                    error[value] = _('Unsupported parameter')
                    raise serializers.ValidationError(error)
        else:
            if value not in self.delta_choices:
                error[value] = _('Unsupported parameter')
                raise serializers.ValidationError(error)
        return value


class OCPCostQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling cost query parameters."""

    DELTA_CHOICES = (('cost', 'cost'))

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    order_by = OrderBySerializer(required=False)

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
