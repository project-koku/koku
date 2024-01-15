#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for settings cost groups."""
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer
from api.report.serializers import FilterSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OpenshiftCostCategory


class CostGroupFilterSerializer(FilterSerializer):
    """Serializer for Cost Group Settings."""

    project = StringOrListField(child=serializers.CharField(), required=False)
    group = StringOrListField(child=serializers.CharField(), required=False)
    default = serializers.BooleanField(required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)


class CostGroupExcludeSerializer(ExcludeSerializer):
    """Serializer for Cost Group Settings."""

    project = serializers.CharField(required=False)
    group = serializers.CharField(required=False)
    default = serializers.BooleanField(required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)


class CostGroupOrderSerializer(OrderSerializer):
    """Serializer for Cost Group Settings."""

    ORDER_CHOICES = (("asc", "asc"), ("desc", "desc"))

    project = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    group = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    default = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)


class CostGroupQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    FILTER_SERIALIZER = CostGroupFilterSerializer
    EXCLUDE_SERIALIZER = CostGroupExcludeSerializer
    ORDER_BY_SERIALIZER = CostGroupOrderSerializer

    order_by_allowlist = frozenset(("project", "group", "default"))


class CostGroupProjectSerializer(serializers.Serializer):
    project = serializers.CharField()
    group = serializers.CharField()

    def _is_valid_field_value(self, model, data: str, field_name: str) -> None:
        """Check that the provided data matches a value in the model field.

        Raises a ValidationError if the data is not found in the model field.
        """

        valid_values = sorted(model.objects.values_list(field_name, flat=True).distinct())
        if data not in valid_values:
            msg = "Select a valid choice"
            if 0 < len(valid_values) < 7:
                verb = "Choice is" if len(valid_values) == 1 else "Choices are"
                msg = f"{msg}. {verb} {', '.join(valid_values)}."
            else:
                msg = f"{msg}. '{data}' is not a valid choice."

            raise serializers.ValidationError(msg)

    def validate_project(self, data):
        self._is_valid_field_value(OCPProject, data, "project")

        return data

    def validate_group(self, data):
        self._is_valid_field_value(OpenshiftCostCategory, data, "name")

        return data
