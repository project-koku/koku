#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HCS Report Serializers."""
from rest_framework import serializers

from reporting.hcs.models import HCSReport


class HCSReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = HCSReport
        fields = ["task_uuid", "created_timestamp", "completed_timestamp", "report_location", "provider"]
