#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tag serializers."""
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import handle_invalid_fields
from api.report.serializers import ParamSerializer
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field


class FilterSerializer(BaseFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    key = StringOrListField(required=False)
    value = StringOrListField(required=False)


class ExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    key = StringOrListField(required=False)
    value = StringOrListField(required=False)


class TagsQueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    EXCLUDE_SERIALIZER = ExcludeSerializer
    FILTER_SERIALIZER = FilterSerializer

    exclude = ExcludeSerializer(required=False)
    filter = FilterSerializer(required=False)
    key_only = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(required=False, min_value=1)
    offset = serializers.IntegerField(required=False, min_value=0)

    # DateField defaults: format='iso-8601', input_formats=['iso-8601']
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

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
        handle_invalid_fields(self, data)

        return data

    def validate_exclude(self, value):
        """Validate incoming exclude data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if exclude field inputs are invalid

        """
        validate_field(self, "exclude", self.EXCLUDE_SERIALIZER, value)
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
        validate_field(self, "filter", self.FILTER_SERIALIZER, value)
        return value
