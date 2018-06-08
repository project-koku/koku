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
from django.utils.translation import ugettext as _
from rest_framework import serializers


def handle_invalid_fields(this, data):
    """Validate incoming data."""
    unknown_keys = None
    if hasattr(this, 'initial_data'):
        unknown_keys = set(this.initial_data.keys()) - set(this.fields.keys())
    if unknown_keys:
        error = {}
        for unknown_key in unknown_keys:
            error[unknown_key] = _('Unsupported parameter')
        raise serializers.ValidationError(error)
    return data


def validate_field(this, field, serializer_cls, value):
    """Validate the provided fields."""
    field_param = this.initial_data.get(field)
    serializer = serializer_cls(data=field_param)
    serializer.is_valid(raise_exception=True)
    return value


class StringOrListField(serializers.ListField):
    """Serializer field to handle types that are string or list.

    Converts everything to a list.
    """

    def to_internal_value(self, data):
        """Handle string data then call super."""
        list_data = data
        if isinstance(data, str):
            list_data = [data]
        return super().to_internal_value(list_data)


class GroupBySerializer(serializers.Serializer):
    """Serializer for handling query parameter group_by."""

    account = StringOrListField(child=serializers.CharField(),
                                required=False)
    instance_type = StringOrListField(child=serializers.CharField(),
                                      required=False)
    service = StringOrListField(child=serializers.CharField(),
                                required=False)
    storage_type = StringOrListField(child=serializers.CharField(),
                                     required=False)

    def validate(self, data):
        """Validate incoming data."""
        handle_invalid_fields(self, data)
        return data


class OrderBySerializer(serializers.Serializer):
    """Serializer for handling query parameter order_by."""

    ORDER_CHOICES = (('asc', 'asc'), ('desc', 'desc'))
    cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                   required=False)
    inventory = serializers.ChoiceField(choices=ORDER_CHOICES,
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
    resolution = serializers.ChoiceField(choices=RESOLUTION_CHOICES,
                                         required=False)
    time_scope = serializers.ChoiceField(choices=TIME_CHOICES,
                                         required=False)
    resource_scope = StringOrListField(child=serializers.CharField(),
                                       required=False)

    def validate(self, data):
        """Validate incoming data."""
        handle_invalid_fields(self, data)

        resolution = data.get('resolution')
        time_scope = data.get('time_scope')

        if resolution and time_scope:
            msg = 'Valid values are {} when resolution is {}'
            if (resolution == 'daily' and
                    (time_scope == '-1' or time_scope == '-2')):
                valid_values = ['-10', '-30']
                valid_vals = ', '.join(valid_values)
                error = {'time_scope': msg.format(valid_vals, 'daily')}
                raise serializers.ValidationError(error)
            if (resolution == 'monthly' and
                    (time_scope == '-10' or time_scope == '-30')):
                valid_values = ['-1', '-2']
                valid_vals = ', '.join(valid_values)
                error = {'time_scope': msg.format(valid_vals, 'monthly')}
                raise serializers.ValidationError(error)
        return data


class QueryParamSerializer(serializers.Serializer):
    """Serializer for handling query parameters."""

    group_by = GroupBySerializer(required=False)
    order_by = OrderBySerializer(required=False)
    filter = FilterSerializer(required=False)

    def validate(self, data):
        """Validate incoming data."""
        handle_invalid_fields(self, data)
        return data

    def validate_group_by(self, value):
        """Validate incoming group_by data."""
        validate_field(self, 'group_by', GroupBySerializer, value)
        return value

    def validate_order_by(self, value):
        """Validate incoming order_by data."""
        validate_field(self, 'order_by', OrderBySerializer, value)
        return value

    def validate_filter(self, value):
        """Validate incoming filter data."""
        validate_field(self, 'filter', FilterSerializer, value)
        return value
