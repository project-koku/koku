#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-Azure Report Serializers."""
import api.report.azure.serializers as azureser
import api.report.ocp.serializers as ocpser


class OCPAzureGroupBySerializer(azureser.AzureGroupBySerializer, ocpser.OCPGroupBySerializer):
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


class OCPAzureOrderBySerializer(azureser.AzureOrderBySerializer, ocpser.OCPOrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAzureFilterSerializer(azureser.AzureFilterSerializer, ocpser.OCPFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = (
        "subscription_guid",
        "resource_location",
        "instance_type",
        "service_name",
        "project",
        "cluster",
        "node",
    )


class OCPAzureExcludeSerializer(azureser.AzureExcludeSerializer, ocpser.OCPExcludeSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = (
        "subscription_guid",
        "resource_location",
        "instance_type",
        "service_name",
        "project",
        "cluster",
        "node",
    )


class OCPAzureQueryParamSerializer(azureser.AzureQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPAzureGroupBySerializer
    ORDER_BY_SERIALIZER = OCPAzureOrderBySerializer
    FILTER_SERIALIZER = OCPAzureFilterSerializer
    EXCLUDE_SERIALIZER = OCPAzureExcludeSerializer
