#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for StaticExchangeRate CRUD."""
import calendar
import logging

from django.conf import settings
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

STATIC_RATE_STATUS_EXPIRED = "expired"
STATIC_RATE_STATUS_ACTIVE = "active"
STATIC_RATE_STATUS_UPCOMING = "upcoming"


def current_utc_month_start():
    """First day of the current UTC month."""
    return timezone.now().date().replace(day=1)


def next_month_start(month_start):
    """First day of the month after ``month_start``."""
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1, day=1)
    return month_start.replace(month=month_start.month + 1, day=1)


def static_rate_status(start_date, end_date, *, current_month_start=None):
    """Lifecycle of a static rate vs the current UTC month.

    * ``expired`` — window ends before the current month
    * ``upcoming`` — window starts in a future month
    * ``active`` — window includes the current UTC month

    Status is for UI labels only. Past-month rates remain editable and
    deletable (see ``static_rate_can_edit`` / ``static_rate_can_delete``).
    """
    if current_month_start is None:
        current_month_start = current_utc_month_start()
    if end_date < current_month_start:
        return STATIC_RATE_STATUS_EXPIRED
    if start_date >= next_month_start(current_month_start):
        return STATIC_RATE_STATUS_UPCOMING
    return STATIC_RATE_STATUS_ACTIVE


def user_can_mutate_static_rates(request):
    """True when the user can PUT/DELETE static rates.

    Mirrors ``CostModelsAccessPermission`` write rules for static-rate URLs
    (no ``/cost-models/{uuid}/`` in the path, so only ``cost_model.write: ["*"]``
    or enhanced org admin grants access). Date windows no longer block mutate
    after COST-8378; these flags exist so the UI can avoid 403 probes.
    """
    if request is None:
        return False
    user = getattr(request, "user", None)
    if user is None:
        return False
    if settings.ENHANCED_ORG_ADMIN and getattr(user, "admin", False):
        return True
    access = getattr(user, "access", None)
    if not access:
        return False
    return "*" in access.get("cost_model", {}).get("write", [])


def static_rate_can_edit(end_date=None, *, current_month_start=None, request=None):
    """True when PUT would be allowed for this user (RBAC)."""
    return user_can_mutate_static_rates(request)


def static_rate_can_delete(start_date=None, *, current_month_start=None, request=None):
    """True when DELETE would be allowed for this user (RBAC)."""
    return user_can_mutate_static_rates(request)


class NumericDecimalField(serializers.DecimalField):
    """Serialize Decimals as JSON numbers.

    coerce_to_string=False keeps a Decimal so the JSON encoder emits a number
    instead of a quoted decimal string.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("coerce_to_string", False)
        super().__init__(**kwargs)


class StaticExchangeRateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating static exchange rates."""

    name = serializers.CharField(read_only=True)
    exchange_rate = NumericDecimalField(max_digits=33, decimal_places=15)
    status = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

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
            "status",
            "can_edit",
            "can_delete",
            "created_timestamp",
            "updated_timestamp",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "can_edit",
            "can_delete",
            "created_timestamp",
            "updated_timestamp",
        ]

    def _current_month_start(self):
        if not hasattr(self, "_cached_current_month_start"):
            self._cached_current_month_start = current_utc_month_start()
        return self._cached_current_month_start

    def get_status(self, instance):
        return static_rate_status(
            instance.start_date, instance.end_date, current_month_start=self._current_month_start()
        )

    def get_can_edit(self, instance):
        return static_rate_can_edit(
            instance.end_date,
            current_month_start=self._current_month_start(),
            request=self.context.get("request"),
        )

    def get_can_delete(self, instance):
        return static_rate_can_delete(
            instance.start_date,
            current_month_start=self._current_month_start(),
            request=self.context.get("request"),
        )

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

    def _validate_update(self, base):
        """Validate constraints specific to updating an existing rate."""
        if base != self.instance.base_currency:
            raise serializers.ValidationError(
                "Base currency cannot be modified. Delete and recreate the exchange rate instead."
            )

    def validate(self, attrs):
        base = attrs.get("base_currency")
        target = attrs.get("target_currency")
        start = attrs.get("start_date")
        end = attrs.get("end_date")

        if base == target:
            raise serializers.ValidationError("Base currency and target currency must be different.")

        if end < start:
            raise serializers.ValidationError("End date must be on or after start date.")

        if self.instance:
            self._validate_update(base)

        # Past-month windows are allowed: create/update/delete may cover already-closed
        # billing months. Finalized *dynamic* monthly rates remain locked separately;
        # static CRUD rewrites STATIC MonthlyExchangeRate rows for affected months.

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
