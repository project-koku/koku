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
"""Common serializer logic."""
from django.utils.translation import ugettext as _
from rest_framework import serializers


def handle_invalid_fields(this, data):
    """Validate incoming data.

    The primary validation being done is ensuring the incoming data only
    contains known fields.

    Args:
        this    (Object): Serializer object
        data    (Dict): data to be validated
    Returns:
        (Dict): Validated data
    Raises:
        (ValidationError): if field inputs are invalid
    """
    unknown_keys = None
    if hasattr(this, 'initial_data'):
        unknown_keys = set(this.initial_data.keys()) - set(this.fields.keys())

    if unknown_keys:
        error = {}
        for unknown_key in unknown_keys:
            error[unknown_key] = _('Unsupported parameter')
        raise serializers.ValidationError(error)
    return data


def validate_field(this, field, serializer_cls, value, **kwargs):
    """Validate the provided fields.

    Args:
        field    (String): the field to be validated
        serializer_cls (Class): a serializer class for validation
        value    (Object): the field value
    Returns:
        (Dict): Validated value
    Raises:
        (ValidationError): if field inputs are invalid
    """
    field_param = this.initial_data.get(field)
    serializer = serializer_cls(data=field_param, **kwargs)
    serializer.is_valid(raise_exception=True)
    return value


def add_operator_specified_fields(fields, field_list):
    """Add the specified and: and or: fields to the serialzer."""
    and_fields = {'and:' + field: StringOrListField(child=serializers.CharField(),
                                                    required=False)
                  for field in field_list}
    or_fields = {'or:' + field: StringOrListField(child=serializers.CharField(),
                                                  required=False)
                 for field in field_list}
    fields.update(and_fields)
    fields.update(or_fields)
    return fields


class StringOrListField(serializers.ListField):
    """Serializer field to handle types that are string or list.

    Converts everything to a list.
    """

    def to_internal_value(self, data):
        """Handle string data then call super.

        Args:
            data    (String or List): data to be converted
        Returns:
            (List): Transformed data
        """
        list_data = data
        if isinstance(data, str):
            list_data = [data]
        # Allow comma separated values for a query param
        if isinstance(list_data, list) and list_data:
            list_data = ','.join(list_data)
            list_data = list_data.split(',')

        return super().to_internal_value(list_data)


class BaseSerializer(serializers.Serializer):
    """A common serializer base for all of our serializers."""

    _opfields = None

    def __init__(self, *args, **kwargs):
        """Initialize the FilterSerializer."""
        tag_keys = kwargs.pop('tag_keys', None)
        super().__init__(*args, **kwargs)

        if tag_keys is not None:
            tag_keys = {key: StringOrListField(child=serializers.CharField(),
                                               required=False)
                        for key in tag_keys}
            # Add tag keys to allowable fields
            self.fields.update(tag_keys)

        if self._opfields:
            add_operator_specified_fields(self.fields, self._opfields)

    def validate(self, data):
        """Validate incoming data."""
        handle_invalid_fields(self, data)
        return data


class FilterSerializer(BaseSerializer):
    """A base serializer for filter operations."""

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
    offset = serializers.IntegerField(required=False, min_value=0)

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


class GroupSerializer(BaseSerializer):
    """A base serializer for group-by operations."""

    pass


class OrderSerializer(BaseSerializer):
    """A base serializer for order-by operations."""

    ORDER_CHOICES = (('asc', 'asc'), ('desc', 'desc'))

    cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                   required=False)
    infrastructure_cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                                  required=False)
    derived_cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                           required=False)
    delta = serializers.ChoiceField(choices=ORDER_CHOICES,
                                    required=False)


class ParamSerializer(BaseSerializer):
    """A base serializer for query parameter operations."""

    # Adding pagination fields to the serializer because we validate
    # before running reports and paginating
    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the query param serializer."""
        if self.tag_keys and self.tag_fields:
            inst = {}
            for key, val in self.tag_fields.items():
                # replace class references with instances of the class.
                inst[key] = val(required=False, tag_keys=self.tag_keys)
            self.fields.update(inst)
        super().__init__(*args, **kwargs)

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
