#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HCS Report Serializers."""
import logging

from rest_framework import serializers

from api.common import error_obj
from reporting.hcs.models import HCSReport

LOG = logging.getLogger(__name__)

HCS_PROVIDER_LIST = ["aws", "aws-local"]


class HCSReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = HCSReport
        fields = ["uuid", "created_timestamp", "completed_timestamp", "reports_list", "provider"]

    def validate(self, data):
        """
        Check for supported providers.
        """
        source_type = data.get("provider").type
        if source_type.lower() in HCS_PROVIDER_LIST:
            return data
        key = "source_type"
        message = f"Invalid source_type, {source_type}, provided."
        raise serializers.ValidationError(error_obj(key, message))
