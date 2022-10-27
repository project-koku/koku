#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.report.serializers import add_operator_specified_fields
from api.tags.gcp.serializers import GCP_FILTER_OP_FIELDS
from api.tags.gcp.serializers import GCPExcludeSerializer
from api.tags.gcp.serializers import GCPFilterSerializer
from api.tags.gcp.serializers import GCPTagsQueryParamSerializer
from api.tags.ocp.serializers import OCP_FILTER_OP_FIELDS
from api.tags.ocp.serializers import OCPExcludeSerializer
from api.tags.ocp.serializers import OCPFilterSerializer
from api.tags.ocp.serializers import OCPTagsQueryParamSerializer


class OCPGCPFilterSerializer(GCPFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPGCPFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPGCPExcludeSerializer(GCPExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPGCPExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPGCPTagsQueryParamSerializer(GCPTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-GCP tag query parameters."""

    exclude = OCPGCPExcludeSerializer(required=False)
    filter = OCPGCPFilterSerializer(required=False)
