#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Organizations serializers."""
from rest_framework import serializers

from api.report.serializers import add_operator_specified_fields
from api.report.serializers import handle_invalid_fields
from api.report.serializers import ParamSerializer
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field
from api.utils import DateHelper
from api.utils import materialized_view_month_start

AWS_FILTER_OP_FIELDS = ["org_unit_id"]


class FilterSerializer(serializers.Serializer):
    """Serializer for handling org query parameter filter."""

    RESOLUTION_CHOICES = (("daily", "daily"), ("monthly", "monthly"))
    TIME_CHOICES = (("-10", "-10"), ("-30", "-30"), ("-1", "-1"), ("-2", "-2"))
    TIME_UNIT_CHOICES = (("day", "day"), ("month", "month"))

    resolution = serializers.ChoiceField(choices=RESOLUTION_CHOICES, required=False)
    time_scope_value = serializers.ChoiceField(choices=TIME_CHOICES, required=False)
    time_scope_units = serializers.ChoiceField(choices=TIME_UNIT_CHOICES, required=False)
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

        resolution = data.get("resolution")
        time_scope_value = data.get("time_scope_value")
        time_scope_units = data.get("time_scope_units")

        if time_scope_units and time_scope_value:
            msg = "Valid values are {} when time_scope_units is {}"
            if time_scope_units == "day" and time_scope_value in ["-1", "-2"]:  # noqa: W504
                valid_values = ["-10", "-30"]
                valid_vals = ", ".join(valid_values)
                error = {"time_scope_value": msg.format(valid_vals, "day")}
                raise serializers.ValidationError(error)
            if time_scope_units == "day" and resolution == "monthly":
                valid_values = ["daily"]
                valid_vals = ", ".join(valid_values)
                error = {"resolution": msg.format(valid_vals, "day")}
                raise serializers.ValidationError(error)
            if time_scope_units == "month" and time_scope_value in ["-10", "-30"]:  # noqa: W504
                valid_values = ["-1", "-2"]
                valid_vals = ", ".join(valid_values)
                error = {"time_scope_value": msg.format(valid_vals, "month")}
                raise serializers.ValidationError(error)

        return data


class AWSOrgFilterSerializer(FilterSerializer):
    """Serializer for handling org query parameter filter."""

    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AWSOrgFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS)


class OrgQueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

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

    def validate_start_date(self, value):
        """Validate that the start_date is within the expected range."""
        dh = DateHelper()
        if value >= materialized_view_month_start(dh).date() and value <= dh.today.date():
            return value

        error = "Parameter start_date must be from {} to {}".format(dh.last_month_start.date(), dh.today.date())
        raise serializers.ValidationError(error)

    def validate_end_date(self, value):
        """Validate that the end_date is within the expected range."""
        dh = DateHelper()
        if value >= materialized_view_month_start(dh).date() and value <= dh.today.date():
            return value
        error = "Parameter end_date must be from {} to {}".format(dh.last_month_start.date(), dh.today.date())
        raise serializers.ValidationError(error)


class AWSOrgQueryParamSerializer(OrgQueryParamSerializer):
    """Serializer for handling AWS org query parameters."""

    filter = AWSOrgFilterSerializer(required=False)

    def validate_filter(self, value):
        """Validate incoming filter data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter field inputs are invalid

        """
        validate_field(self, "filter", AWSOrgFilterSerializer, value)
        return value
