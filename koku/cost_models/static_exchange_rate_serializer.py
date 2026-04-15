#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for StaticExchangeRate with MonthlyExchangeRate side effects."""
import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import transaction
from rest_framework import serializers

from api.common import log_json
from api.currency.currencies import VALID_CURRENCIES
from api.currency.models import ExchangeRateDictionary
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types

LOG = logging.getLogger(__name__)


def _iter_months(start_date, end_date):
    """Yield the first day of each month between start_date and end_date inclusive."""
    current = start_date.replace(day=1)
    end = end_date.replace(day=1)
    while current <= end:
        yield current
        current += relativedelta(months=1)


def _upsert_monthly_rates(static_rate):
    """Upsert MonthlyExchangeRate rows with rate_type=static for each month in the validity period."""
    for month_start in _iter_months(static_rate.start_date, static_rate.end_date):
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=month_start,
            base_currency=static_rate.base_currency,
            target_currency=static_rate.target_currency,
            defaults={
                "exchange_rate": static_rate.exchange_rate,
                "rate_type": RateType.STATIC,
            },
        )


def _remove_static_and_backfill_dynamic(base_currency, target_currency, start_date, end_date):
    """Remove static rows for affected months and backfill with dynamic rates from ExchangeRateDictionary."""
    MonthlyExchangeRate.objects.filter(
        effective_date__gte=start_date.replace(day=1),
        effective_date__lte=end_date.replace(day=1),
        base_currency=base_currency,
        target_currency=target_currency,
        rate_type=RateType.STATIC,
    ).delete()

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return

    exchange_dict = erd.currency_exchange_dictionary
    rate = exchange_dict.get(base_currency, {}).get(target_currency)
    if rate is None:
        return

    for month_start in _iter_months(start_date, end_date):
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=month_start,
            base_currency=base_currency,
            target_currency=target_currency,
            defaults={
                "exchange_rate": rate,
                "rate_type": RateType.DYNAMIC,
            },
        )


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

    def validate_base_currency(self, value):
        value = value.upper()
        if value not in VALID_CURRENCIES:
            raise serializers.ValidationError(f"Invalid currency code: {value}")
        return value

    def validate_target_currency(self, value):
        value = value.upper()
        if value not in VALID_CURRENCIES:
            raise serializers.ValidationError(f"Invalid currency code: {value}")
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
                raise serializers.ValidationError(
                    "Overlapping validity period exists for this currency pair."
                )

        return data

    def _get_schema_name(self):
        request = self.context.get("request")
        if request and hasattr(request, "user") and hasattr(request.user, "customer"):
            return request.user.customer.schema_name
        return None

    @transaction.atomic
    def create(self, validated_data):
        instance = StaticExchangeRate.objects.create(**validated_data)
        _upsert_monthly_rates(instance)
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
            _remove_static_and_backfill_dynamic(old_base, old_target, old_start, old_end)

        _upsert_monthly_rates(instance)

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

    @transaction.atomic
    def delete(self, instance):
        _remove_static_and_backfill_dynamic(
            instance.base_currency,
            instance.target_currency,
            instance.start_date,
            instance.end_date,
        )
        pair_name = instance.name
        instance.delete()
        schema_name = self._get_schema_name()
        if schema_name:
            invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
        LOG.info(log_json(msg="Static exchange rate deleted", pair=pair_name))
