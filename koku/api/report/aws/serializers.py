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
"""AWS Report Serializers."""
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

    _opfields = ('account', 'az', 'instance_type', 'region',
                 'service', 'storage_type', 'product_family')

    # account field will accept both account number and account alias.
    account = StringOrListField(child=serializers.CharField(),
                                required=False)
    az = StringOrListField(child=serializers.CharField(),
                           required=False)
    instance_type = StringOrListField(child=serializers.CharField(),
                                      required=False)
    region = StringOrListField(child=serializers.CharField(),
                               required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)
    storage_type = StringOrListField(child=serializers.CharField(),
                                     required=False)
    product_family = StringOrListField(child=serializers.CharField(),
                                       required=False)


class OrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ('usage', 'account_alias', 'region', 'service', 'product_family')

    usage = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                    required=False)
    # ordering by alias is supported, but ordering by account is not due to the
    # probability that a human-recognizable alias is more useful than account number.
    account_alias = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                            required=False)
    region = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                     required=False)
    service = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                      required=False)
    product_family = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES,
                                             required=False)


class FilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ('account', 'service', 'region', 'az', 'product_family')

    account = StringOrListField(child=serializers.CharField(),
                                required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)
    region = StringOrListField(child=serializers.CharField(),
                               required=False)
    az = StringOrListField(child=serializers.CharField(),
                           required=False)
    product_family = StringOrListField(child=serializers.CharField(),
                                       required=False)


class QueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    DELTA_CHOICES = (
        ('usage', 'usage'),
        ('cost', 'cost')
    )

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    units = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AWS query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=FilterSerializer,
                                 group_by=GroupBySerializer,
                                 order_by=OrderBySerializer)

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
