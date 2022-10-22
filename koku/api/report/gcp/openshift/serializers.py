#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-GCP Report Serializers."""
from rest_framework import serializers

import api.report.gcp.serializers as gcpser
import api.report.ocp.serializers as ocpser
from api.report.serializers import StringOrListField


class OCPGCPGroupBySerializer(gcpser.GCPGroupBySerializer, ocpser.OCPGroupBySerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("account", "region", "service", "project", "instance_type", "cluster", "node", "gcp_project")


class OCPGCPOrderBySerializer(gcpser.GCPOrderBySerializer, ocpser.OCPOrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPGCPFilterSerializer(gcpser.GCPFilterSerializer, ocpser.OCPFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("account", "region", "service", "project", "instance_type", "cluster", "node", "gcp_project")

    instance_type = StringOrListField(child=serializers.CharField(), required=False)


class OCPGCPExcludeSerializer(gcpser.GCPExcludeSerializer, ocpser.OCPExcludeSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("account", "region", "service", "project", "instance_type", "cluster", "node", "gcp_project")

    instance_type = StringOrListField(child=serializers.CharField(), required=False)


class OCPGCPQueryParamSerializer(gcpser.GCPQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPGCPGroupBySerializer
    ORDER_BY_SERIALIZER = OCPGCPOrderBySerializer
    FILTER_SERIALIZER = OCPGCPFilterSerializer
    EXCLUDE_SERIALIZER = OCPGCPExcludeSerializer
