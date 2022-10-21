#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-Azure Report Serializers."""
import api.report.azure.serializers as azureser
import api.report.ocp.serializers as ocpser


class OCPAzureGroupBySerializer(azureser.AzureGroupBySerializer, ocpser.GroupBySerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = (
        "subscription_guid",
        "resource_location",
        "instance_type",
        "service_name",
        "project",
        "cluster",
        "node",
    )


class OCPAzureOrderBySerializer(azureser.AzureOrderBySerializer, ocpser.OrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAzureFilterSerializer(azureser.AzureFilterSerializer, ocpser.FilterSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAzureExcludeSerializer(azureser.AzureExcludeSerializer, ocpser.ExcludeSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAzureQueryParamSerializer(azureser.AzureQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPAzureGroupBySerializer
    ORDER_BY_SERIALIZER = OCPAzureOrderBySerializer
    FILTER_SERIALIZER = OCPAzureFilterSerializer
    EXCLUDE_SERIALIZER = OCPAzureExcludeSerializer
