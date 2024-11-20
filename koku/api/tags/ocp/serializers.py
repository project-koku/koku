#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.utils.translation import gettext
from rest_framework import serializers

from api.report.serializers import add_operator_specified_fields
from api.report.serializers import StringOrListField
from api.tags.serializers import ExcludeSerializer
from api.tags.serializers import FilterSerializer
from api.tags.serializers import TagsQueryParamSerializer


OCP_FILTER_OP_FIELDS = ["project", "enabled", "cluster", "category"]


class OCPFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    TYPE_CHOICES = (("pod", "pod"), ("storage", "storage"), ("*", "*"))
    type = serializers.ChoiceField(choices=TYPE_CHOICES, required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)
    virtualization = serializers.BooleanField(default=False, required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    vm_name = StringOrListField(child=serializers.CharField(), required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCPFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCP_FILTER_OP_FIELDS)

    def validate(self, data):
        if data.get("vm_name") and not data.get("virtualization"):
            err_msg = "filter vm_name must be used with virtualization filter"
            error = {"missing_requirement": gettext(err_msg)}
            raise serializers.ValidationError(error)
        return super().validate(data)


class OCPExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    TYPE_CHOICES = (("pod", "pod"), ("storage", "storage"), ("*", "*"))
    type = serializers.ChoiceField(choices=TYPE_CHOICES, required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCPExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCP_FILTER_OP_FIELDS)


class OCPTagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling OCP tag query parameters."""

    EXCLUDE_SERIALIZER = OCPExcludeSerializer
    FILTER_SERIALIZER = OCPFilterSerializer

    exclude = OCPExcludeSerializer(required=False)
    filter = OCPFilterSerializer(required=False)
