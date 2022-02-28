#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from reporting.user_settings.models import UserSettings


class UserSettingSerializer(serializers.Serializer):
    """Serializer for CostUsageReportManifest."""

    class Meta:
        model = UserSettings

    settings = serializers.JSONField()
