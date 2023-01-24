#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Minimal Report Serializers."""
import logging

from rest_framework import serializers

from api.common import error_obj
from reporting.minimal_report.models import MinimalReport

LOG = logging.getLogger(__name__)

PROVIDER_LIST = ["aws", "aws-local"]


class MinimalReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MinimalReport
        fields = ["uuid", "created_timestamp", "completed_timestamp", "reports_list", "source"]

    def validate(self, data):
        """
        Check for supported sources.
        """
        source_type = data.get("source").type
        if source_type.lower() in PROVIDER_LIST:
            return data
        key = "source_type"
        message = f"Invalid source_type, {source_type}, provided."
        raise serializers.ValidationError(error_obj(key, message))
