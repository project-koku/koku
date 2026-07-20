#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for StaticExchangeRate CRUD."""
import calendar
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from api.common import log_json
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import StaticExchangeRate
from cost_models.monthly_exchange_rate_utils import replace_static_to_dynamic_monthly_rates
from cost_models.monthly_exchange_rate_utils import upsert_static_monthly_rates
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types

LOG = logging.getLogger(__name__)


class TrailingZeroStrippingDecimalField(serializers.DecimalField):
    """Serialize Decimals as strings without unnecessary trailing zeros.

    Storage keeps full DecimalField precision; only the API representation is trimmed.
    """

    def to_representation(self, value):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(value)
        return format(value.normalize(), "f")


class StaticExchangeRateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating static exchange rates."""

    name = serializers.CharField(read_only=True)
    exchange_rate = TrailingZeroStrippingDecimalField(max_digits=33, decimal_places=15)

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
        read_only_fields = ["uuid", "created_timestamp", "updated_timestamp"]

    def _validate_currency_code(self, value):
        code = value.upper()
        if not is_valid_iso_currency(code):
            raise serializers.ValidationError(f'"{code}" is not a valid ISO 4217 currency.')
        return code

    def validate_base_currency(self, value):
        return self._validate_currency_code(value)

    def validate_target_currency(self, value):
        return self._validate_currency_code(value)

    def validate_exchange_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError("Exchange rate must be strictly positive.")
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

    def _validate_update(self, base, target, start, end, current_month_start, has_finalized_months):
        """Validate constraints specific to updating an existing rate."""
        if self.instance.end_date < current_month_start:
            raise serializers.ValidationError(
                f"This rate ended on {self.instance.end_date} and all its months have been finalized. "
                "To set a new rate, create a new record starting from the current month."
            )
        if has_finalized_months:
            if base != self.instance.base_currency or target != self.instance.target_currency:
                raise serializers.ValidationError(
                    "Currencies cannot be changed because this rate has finalized months."
                )
            if start != self.instance.start_date:
                raise serializers.ValidationError(
                    "start_date cannot be changed because this rate has finalized months. "
                    "Shrink the end_date instead, then create a new rate for the remaining period."
                )
            min_end_date = current_month_start - timedelta(days=1)
            if end < min_end_date:
                raise serializers.ValidationError(
                    "end_date cannot be earlier than the previous month when shrinking a finalized rate."
                )

    def validate(self, attrs):
        base = attrs.get("base_currency")
        target = attrs.get("target_currency")
        start = attrs.get("start_date")
        end = attrs.get("end_date")

        if base == target:
            raise serializers.ValidationError("base_currency and target_currency must be different.")

        if end < start:
            raise serializers.ValidationError("end_date must be on or after start_date.")

        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        has_finalized_months = self.instance and self.instance.start_date < current_month_start
        if self.instance:
            self._validate_update(base, target, start, end, current_month_start, has_finalized_months)

        if not has_finalized_months and start < current_month_start:
            raise serializers.ValidationError("start_date cannot be in a past month.")

        overlapping = StaticExchangeRate.objects.filter(
            base_currency=base,
            target_currency=target,
            start_date__lte=end,
            end_date__gte=start,
        )
        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)
        overlap = overlapping.first()
        if overlap:
            raise serializers.ValidationError(
                f"Overlaps with existing rate {overlap.base_currency}-{overlap.target_currency} "
                f"({overlap.start_date} to {overlap.end_date})."
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)
        upsert_static_monthly_rates(instance)
        # Defer cache invalidation until after this atomic block commits,
        # so concurrent requests don't re-cache stale data from an uncommitted transaction.
        schema_name = self.context["request"].user.customer.schema_name
        transaction.on_commit(lambda: invalidate_view_cache_for_tenant_and_all_source_types(schema_name))
        LOG.info(
            log_json(
                msg="Static exchange rate created with MonthlyExchangeRate rows",
                pair=instance.name,
                start=str(instance.start_date),
                end=str(instance.end_date),
            )
        )
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        old_base = instance.base_currency
        old_target = instance.target_currency
        old_start = instance.start_date
        old_end = instance.end_date

        instance = super().update(instance, validated_data)

        scope_changed = (
            old_base != instance.base_currency
            or old_target != instance.target_currency
            or old_start != instance.start_date
            or old_end != instance.end_date
        )
        # If scope changed, clean up old range and backfill with dynamic rates.
        # upsert_static_monthly_rates will then overwrite overlapping months with the new static values.
        if scope_changed:
            replace_static_to_dynamic_monthly_rates(old_base, old_target, old_start, old_end)

        upsert_static_monthly_rates(instance)

        schema_name = self.context["request"].user.customer.schema_name
        transaction.on_commit(lambda: invalidate_view_cache_for_tenant_and_all_source_types(schema_name))
        LOG.info(
            log_json(
                msg="Static exchange rate updated with MonthlyExchangeRate rows",
                pair=instance.name,
            )
        )
        return instance
