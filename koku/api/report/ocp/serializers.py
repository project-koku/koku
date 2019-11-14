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

from api.report.serializers import (FilterSerializer as BaseFilterSerializer,
                                    GroupSerializer,
                                    OrderSerializer,
                                    ParamSerializer,
                                    StringOrListField,
                                    validate_field)
from api.utils import UnitConverter


class GroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ('project', 'cluster', 'node')

    cluster = StringOrListField(child=serializers.CharField(),
                                required=False)
    project = StringOrListField(child=serializers.CharField(),
                                required=False)
    node = StringOrListField(child=serializers.CharField(),
                             required=False)


class OrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ('project', 'cluster', 'node')

    cluster = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                      required=False)
    project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                      required=False)
    node = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                   required=False)


class InventoryOrderBySerializer(OrderBySerializer):
    """Order By Serializer for CPU and Memory endpoints."""

    _opfields = ('project', 'cluster', 'node', 'usage', 'request', 'limit')

    usage = serializers.ChoiceField(choices=OrderBySerializer.ORDER_CHOICES,
                                    required=False)
    request = serializers.ChoiceField(choices=OrderBySerializer.ORDER_CHOICES,
                                      required=False)
    limit = serializers.ChoiceField(choices=OrderBySerializer.ORDER_CHOICES,
                                    required=False)


class FilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    INFRASTRUCTURE_CHOICES = (
        ('aws', 'aws'),
        ('azure', 'azure'),
    )

    _opfields = ('project', 'cluster', 'node', 'pod', 'infrastructures')

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

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        super().validate(data)

        if data.get('infrastructures'):
            infra_value = data['infrastructures']
            data['infrastructures'] = [infra_value.upper()]

        return data


class OCPQueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    units = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=FilterSerializer,
                                 group_by=GroupBySerializer,
                                 order_by=OrderBySerializer)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        super().validate(data)
        error = {}
        if 'delta' in data.get('order_by', {}) and 'delta' not in data:
            error['order_by'] = _('Cannot order by delta without a delta param')
            raise serializers.ValidationError(error)
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

    delta_fields = (
        'usage',
        'request',
        'limit',
        'capacity'
    )

    delta = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=FilterSerializer,
                                 group_by=GroupBySerializer,
                                 order_by=InventoryOrderBySerializer)

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            value    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid

        """
        super().validate_order_by(value)
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
                if val not in self.delta_fields:
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

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid

        """
        super().validate_order_by(value)
        validate_field(self, 'order_by', OrderBySerializer, value)
        return value
