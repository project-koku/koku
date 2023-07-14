#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.currency.currencies import CURRENCY_CHOICES
from api.user_settings.settings import COST_TYPE_CHOICES
from reporting.user_settings.models import UserSettings


class UserSettingSerializer(serializers.Serializer):
    """Serializer for CostUsageReportManifest."""

    class Meta:
        model = UserSettings

    settings = serializers.JSONField()


class UserSettingUpdateCostTypeSerializer(serializers.Serializer):
    """Serializer for setting cost type."""

    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICES)


class UserSettingUpdateCurrencySerializer(serializers.Serializer):
    """Serializer for setting cost type."""

    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES)
