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
    # the BaseSerializer. This handles the case where a a child class has two
    # parents with differing sets of fields.
    subclasses = serializer_cls.__subclasses__()
    if subclasses and not serializer.is_valid():
        for subcls in subclasses:
            for parent in subcls.__bases__:
                # when using multiple inheritance, the data is valid as long as one
                # parent class validates the data.
                serializer = parent(data=field_param, **kwargs)
                if serializer.is_valid():
                    return value
        raise serializers.ValidationError({field: _('Unsupported parameter')})

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
