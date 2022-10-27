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


GCP_FILTER_OP_FIELDS = ["account", "gcp_project"]


class GCPFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    account = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the GCPFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS)


class GCPExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    account = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the GCPExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS)


class GCPTagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling GCP tag query parameters."""

    EXCLUDE_SERIALIZER = GCPExcludeSerializer
    FILTER_SERIALIZER = GCPFilterSerializer

    exclude = GCPExcludeSerializer(required=False)
    filter = GCPFilterSerializer(required=False)
