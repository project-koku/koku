#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.currency.currencies import CurrencyField
from api.settings.settings import COST_TYPE_CHOICES
from reporting.tenant_settings.models import TenantSettings
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
    """Serializer for setting currency."""

    currency = CurrencyField()


class TenantSettingsSerializer(serializers.Serializer):
    """Serializer for tenant-level data retention settings."""

    data_retention_months = serializers.IntegerField(
        min_value=TenantSettings.MIN_RETENTION_MONTHS,
        max_value=TenantSettings.MAX_RETENTION_MONTHS,
    )


class EnabledCurrencySerializer(serializers.Serializer):
    """Accepts an enabled flag for a single currency (code comes from the URL path)."""

    enabled = serializers.BooleanField()
