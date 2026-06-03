#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for StaticExchangeRate with MonthlyExchangeRate side effects."""
import calendar
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from api.common import log_json
from api.currency.currencies import get_all_iso_currency_codes
from api.currency.currencies import get_currency_info
from api.currency.currencies import get_dynamic_rate_currencies
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import EnabledCurrency
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_utils import remove_static_and_backfill_dynamic
from cost_models.static_exchange_rate_utils import upsert_static_monthly_rates
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types

LOG = logging.getLogger(__name__)


class StaticExchangeRateSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = StaticExchangeRate
        fields = [
            "uuid",
            "name",
            "base_currency",
            "target_currency",
            "exchange_rate",
            "start_date",
            "end_date",
            "created_timestamp",
            "updated_timestamp",
        ]
        read_only_fields = ["uuid", "name", "created_timestamp", "updated_timestamp"]

    def get_name(self, obj):
        return f"{obj.base_currency}-{obj.target_currency}"

    def validate_base_currency(self, value):
        if not is_valid_iso_currency(value):
            raise serializers.ValidationError(f"Invalid currency code: {value}")
        return value.upper()

    def validate_target_currency(self, value):
        if not is_valid_iso_currency(value):
            raise serializers.ValidationError(f"Invalid currency code: {value}")
        return value.upper()

    def validate_exchange_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError("exchange_rate must be greater than zero.")
        return value

    def validate_start_date(self, value):
        if value.day != 1:
            raise serializers.ValidationError("start_date must be the first day of a month.")
        return value

    def validate_end_date(self, value):
        last_day = calendar.monthrange(value.year, value.month)[1]
        if value.day != last_day:
            raise serializers.ValidationError("end_date must be the last day of a month.")
        return value

    def validate(self, data):
        base = data.get("base_currency") or (self.instance.base_currency if self.instance else None)
        target = data.get("target_currency") or (self.instance.target_currency if self.instance else None)
        start = data.get("start_date") or (self.instance.start_date if self.instance else None)
        end = data.get("end_date") or (self.instance.end_date if self.instance else None)

        if base == target:
            raise serializers.ValidationError("base_currency and target_currency must be different.")

        if start > end:
            raise serializers.ValidationError("start_date must be on or before end_date.")

        overlap_qs = StaticExchangeRate.objects.filter(
            base_currency=base,
            target_currency=target,
            start_date__lte=end,
            end_date__gte=start,
        )
        if self.instance:
            overlap_qs = overlap_qs.exclude(uuid=self.instance.uuid)
        if overlap_qs.exists():
            raise serializers.ValidationError("Overlapping validity period exists for this currency pair.")

        current_month_start = timezone.now().date().replace(day=1)
        if start < current_month_start:
            raise serializers.ValidationError(
                "Cannot create or modify exchange rates for past billing periods. "
                "Only the current month and future months may be affected."
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        instance = StaticExchangeRate.objects.create(**validated_data)
        upsert_static_monthly_rates(instance)
        schema_name = self.context["request"].user.customer.schema_name
        invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
        LOG.info(
            log_json(
                msg="Static exchange rate created",
                pair=instance.name,
                start=str(instance.start_date),
                end=str(instance.end_date),
            )
        )
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        old_start = instance.start_date
        old_end = instance.end_date
        old_base = instance.base_currency
        old_target = instance.target_currency

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if (
            old_base != instance.base_currency
            or old_target != instance.target_currency
            or old_start != instance.start_date
            or old_end != instance.end_date
        ):
            remove_static_and_backfill_dynamic(old_base, old_target, old_start, old_end)

        upsert_static_monthly_rates(instance)

        schema_name = self.context["request"].user.customer.schema_name
        invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
        LOG.info(
            log_json(
                msg="Static exchange rate updated",
                pair=instance.name,
            )
        )
        return instance


class CurrencyExchangeRateSerializer(serializers.Serializer):
    """Read-only serializer for a currency grouped with its static exchange rates."""

    code = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    enabled = serializers.BooleanField()
    exchange_rates = StaticExchangeRateSerializer(many=True)

    @classmethod
    def build_grouped_response(cls, queryset):
        """Return all ISO 4217 currencies with exchange rates and enabled status.

        Every known currency is included so the admin can discover, enable,
        and manage exchange rates from a single endpoint.
        """
        enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
        dynamic_codes = get_dynamic_rate_currencies()

        rates_by_code = {}
        for rate in queryset:
            rates_by_code.setdefault(rate.base_currency, []).append(rate)

        result = []
        for code in sorted(get_all_iso_currency_codes()):
            info = get_currency_info(code, dynamic_codes)
            info["enabled"] = code in enabled_codes
            info["exchange_rates"] = StaticExchangeRateSerializer(rates_by_code.get(code, []), many=True).data
            result.append(info)
        return result
