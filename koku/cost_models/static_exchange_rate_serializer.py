#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for StaticExchangeRate with MonthlyExchangeRate side effects."""
import calendar
import logging

from django.db import transaction
from rest_framework import serializers

from api.common import log_json
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_utils import ensure_currencies_enabled
from cost_models.static_exchange_rate_utils import remove_static_and_backfill_dynamic
from cost_models.static_exchange_rate_utils import upsert_monthly_rates
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
            "version",
            "created_timestamp",
            "updated_timestamp",
        ]
        read_only_fields = ["uuid", "name", "version", "created_timestamp", "updated_timestamp"]

    def get_name(self, obj):
        return f"{obj.base_currency}-{obj.target_currency}"

    def _validate_currency_code(self, value):
        value = value.upper()
        if not is_valid_iso_currency(value):
            raise serializers.ValidationError(f"Invalid currency code: {value}")
        return value

    def validate_base_currency(self, value):
        return self._validate_currency_code(value)

    def validate_target_currency(self, value):
        return self._validate_currency_code(value)

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

        if base and target and base == target:
            raise serializers.ValidationError("base_currency and target_currency must be different.")

        if start and end and start > end:
            raise serializers.ValidationError("start_date must be on or before end_date.")

        if base and target and start and end:
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

        return data

    def _get_schema_name(self):
        request = self.context.get("request")
        if request and hasattr(request, "user") and hasattr(request.user, "customer"):
            return request.user.customer.schema_name
        return None

    @transaction.atomic
    def create(self, validated_data):
        instance = StaticExchangeRate.objects.create(**validated_data)
        ensure_currencies_enabled(instance.base_currency, instance.target_currency)
        upsert_monthly_rates(instance)
        schema_name = self._get_schema_name()
        if schema_name:
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

        validated_data["version"] = instance.version + 1

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if old_base != instance.base_currency or old_target != instance.target_currency:
            remove_static_and_backfill_dynamic(old_base, old_target, old_start, old_end)

        ensure_currencies_enabled(instance.base_currency, instance.target_currency)
        upsert_monthly_rates(instance)

        schema_name = self._get_schema_name()
        if schema_name:
            invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
        LOG.info(
            log_json(
                msg="Static exchange rate updated",
                pair=instance.name,
                version=instance.version,
            )
        )
        return instance
