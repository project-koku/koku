#
# Copyright 2019 Red Hat, Inc.
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
"""Azure Report Serializers."""
from pint.errors import UndefinedUnitError
from rest_framework import serializers

from api.report.serializers import (FilterSerializer as BaseFilterSerializer,
                                    GroupSerializer,
                                    OrderSerializer,
                                    ParamSerializer,
                                    StringOrListField,
                                    validate_field)
from api.utils import UnitConverter


class AzureGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ('subscription', 'resource_location', 'resource_type', 'service')

    subscription = StringOrListField(child=serializers.CharField(),
                                     required=False)
    resource_location = StringOrListField(child=serializers.CharField(),
                                          required=False)
    resource_type = StringOrListField(child=serializers.CharField(),
                                      required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)


class AzureOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ('subscription', 'resource_location', 'resource_type', 'service')

    subscription = StringOrListField(child=serializers.CharField(),
                                     required=False)
    resource_location = StringOrListField(child=serializers.CharField(),
                                          required=False)
    resource_type = StringOrListField(child=serializers.CharField(),
                                      required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)


class AzureFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ('subscription', 'resource_location', 'resource_type', 'service')

    subscription = StringOrListField(child=serializers.CharField(),
                                     required=False)
    resource_location = StringOrListField(child=serializers.CharField(),
                                          required=False)
    resource_type = StringOrListField(child=serializers.CharField(),
                                      required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)


class AzureQueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    DELTA_CHOICES = (
        ('usage', 'usage'),
        ('cost', 'cost')
    )

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    units = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the Azure query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=AzureFilterSerializer,
                                 group_by=AzureGroupBySerializer,
                                 order_by=AzureOrderBySerializer)

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        validate_field(self, 'group_by', AzureGroupBySerializer, value,
                       tag_keys=self.tag_keys)
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
        super().validate_order_by(value)
        validate_field(self, 'order_by', AzureOrderBySerializer, value)
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
        validate_field(self, 'filter', AzureFilterSerializer, value,
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

    def validate_delta(self, value):
        """Validate incoming delta value based on path."""
        valid_delta = 'usage'
        request = self.context.get('request')
        if request and 'costs' in request.path:
            valid_delta = 'cost'
        if value != valid_delta:
            error = {'delta': f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value
