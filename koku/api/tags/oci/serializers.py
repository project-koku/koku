#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from rest_framework import serializers

from api.report.serializers import add_operator_specified_fields
from api.report.serializers import StringOrListField
from api.tags.serializers import ExcludeSerializer
from api.tags.serializers import FilterSerializer
from api.tags.serializers import TagsQueryParamSerializer


OCI_FILTER_OP_FIELDS = ["payer_tenant_id"]


class OCIFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCIFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCI_FILTER_OP_FIELDS)


class OCIExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCIExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCI_FILTER_OP_FIELDS)


class OCITagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling OCI tag query parameters."""

    EXCLUDE_SERIALIZER = OCIExcludeSerializer
    FILTER_SERIALIZER = OCIFilterSerializer

    exclude = OCIExcludeSerializer(required=False)
    filter = OCIFilterSerializer(required=False)
