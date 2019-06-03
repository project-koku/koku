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
import copy

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
            error[unknown_key] = _('Unsupported parameter or invalid value')
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

    # extract tag_keys from field_params and recreate the tag_keys param
    tag_keys = None
    if not kwargs.get('tag_keys') and getattr(serializer_cls,
                                              '_tagkey_support', False):
        tag_keys = list(filter(lambda x: 'tag:' in x, field_param))
        kwargs['tag_keys'] = tag_keys

    serializer = serializer_cls(data=field_param, **kwargs)

    # Handle validation of multi-inherited classes.
    #
    # The serializer classes call super(). So, validation happens bottom-up from
    # the BaseSerializer. This handles the case where a child class has two
    # parents with differing sets of fields.
    subclasses = serializer_cls.__subclasses__()
    if subclasses and not serializer.is_valid():
        message = 'Unsupported parameter or invalid value'
        error = serializers.ValidationError({field: _(message)})
        for subcls in subclasses:
            for parent in subcls.__bases__:
                # when using multiple inheritance, the data is valid as long as one
                # parent class validates the data.
                parent_serializer = parent(data=field_param, **kwargs)
                try:
                    parent_serializer.is_valid(raise_exception=True)
                    return value
                except serializers.ValidationError as exc:
                    error = exc
        raise error

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
    _tagkey_support = None

    def __init__(self, *args, **kwargs):
        """Initialize the BaseSerializer."""
        self.tag_keys = kwargs.pop('tag_keys', None)
        super().__init__(*args, **kwargs)

        if self.tag_keys is not None:
            fkwargs = {'child': serializers.CharField(), 'required': False}
            self._init_tag_keys(StringOrListField, fkwargs=fkwargs)

        if self._opfields:
            add_operator_specified_fields(self.fields, self._opfields)

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

    def _init_tag_keys(self, field, fargs=None, fkwargs=None):
        """Initialize tag-based fields.

        Args:
            field (Serializer)
            fargs (list) Serializer's positional args
            fkwargs (dict) Serializer's keyword args

        """
        if fargs is None:
            fargs = []

        if fkwargs is None:
            fkwargs = {}

        tag_fields = {}
        for key in self.tag_keys:
            if len(self.tag_keys) > 1 and 'child' in fkwargs.keys():
                # when there are multiple filters, each filter needs its own
                # instantiated copy of the child field.
                fkwargs['child'] = copy.deepcopy(fkwargs.get('child'))
            tag_fields[key] = field(*fargs, **fkwargs)

        # Add tag keys to allowable fields
        for key, val in tag_fields.items():
            setattr(self, key, val)
            self.fields.update({key: val})


class FilterSerializer(BaseSerializer):
    """A base serializer for filter operations."""

    _tagkey_support = True

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

    _tagkey_support = True


class OrderSerializer(BaseSerializer):
    """A base serializer for order-by operations."""

    _tagkey_support = True

    ORDER_CHOICES = (('asc', 'asc'), ('desc', 'desc'))

    cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                   required=False)
    infrastructure_cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                                  required=False)
    derived_cost = serializers.ChoiceField(choices=ORDER_CHOICES,
                                           required=False)
    delta = serializers.ChoiceField(choices=ORDER_CHOICES,
                                    required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OrderSerializer."""
        super().__init__(*args, **kwargs)

        if self.tag_keys is not None:
            fkwargs = {'choices': OrderSerializer.ORDER_CHOICES,
                       'required': False}
            self._init_tag_keys(serializers.ChoiceField, fkwargs=fkwargs)


class ParamSerializer(BaseSerializer):
    """A base serializer for query parameter operations."""

    _tagkey_support = True

    # Adding pagination fields to the serializer because we validate
    # before running reports and paginating
    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)

    # fields that can be ordered without a corresponding group-by
    order_by_whitelist = ('cost', 'derived_cost', 'infrastructure_cost',
                          'delta', 'usage', 'request', 'limit', 'capacity')

    def _init_tagged_fields(self, **kwargs):
        """Initialize serializer fields that support tagging.

        This method is used by sub-classed __init__() functions for instantiating Filter,
        Order, and Group classes. This enables us to pass our tag keys into the
        serializer.

        Args:
            kwargs (dict) {field_name: FieldObject}

        """
        for key, val in kwargs.items():
            data = {}
            if issubclass(val, FilterSerializer):
                data = self.initial_data.get('filter')
            elif issubclass(val, OrderSerializer):
                data = self.initial_data.get('order_by')
            elif issubclass(val, GroupSerializer):
                data = self.initial_data.get('group_by')

            inst = val(required=False, tag_keys=self.tag_keys, data=data)
            setattr(self, key, inst)
            self.fields[key] = inst

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            value    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid
        """
        error = {}

        for key, val in value.items():
            if key in self.order_by_whitelist:
                continue    # fields that do not require a group-by

            if 'group_by' in self.initial_data:
                group_keys = self.initial_data.get('group_by').keys()
                if key in group_keys:
                    continue    # found matching group-by

                # special case: we order by account_alias, but we group by account.
                if key == 'account_alias' and 'account' in group_keys:
                    continue

            error[key] = _(f'Order-by "{key}" requires matching Group-by.')
            raise serializers.ValidationError(error)
        return value
