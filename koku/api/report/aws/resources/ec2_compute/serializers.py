#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS EC2 ComputeReport Serializers."""
from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer


class AWSEC2ComputeGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    pass


class AWSEC2ComputeOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    pass


class AWSEC2ComputeFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    pass


class AWSEC2ComputeExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    pass


class AWSEC2ComputeQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    pass
