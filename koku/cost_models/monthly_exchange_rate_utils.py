#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utilities for managing MonthlyExchangeRate side effects."""
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from api.common import log_json
from api.currency.models import ExchangeRateDictionary
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate

LOG = logging.getLogger(__name__)


def _iter_months(start_date, end_date):
    """Yield the first day of each month between start_date and end_date inclusive."""
    current = start_date.replace(day=1)
    end = end_date.replace(day=1)
    while current <= end:
        yield current
        current += relativedelta(months=1)


def _explicit_static_rate_exists(base_currency, target_currency, month_start):
    """Check if a StaticExchangeRate explicitly defines this direction covering the given month."""
    return StaticExchangeRate.objects.filter(
        base_currency=base_currency,
        target_currency=target_currency,
        start_date__lte=month_start,
        end_date__gte=month_start,
    ).exists()


def upsert_static_monthly_rates(static_rate):
    """Upsert MonthlyExchangeRate rows for each month, including the inverse direction.

    The forward direction is always written unconditionally. The inverse (1/rate)
    is written only when no explicit StaticExchangeRate defines the reverse pair
    for that month, ensuring explicit user-defined rates always take precedence.
    """
    if static_rate.exchange_rate <= 0:
        raise ValueError(f"exchange_rate must be positive, got {static_rate.exchange_rate}")
    inverse_rate = Decimal(1) / static_rate.exchange_rate

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

        if not _explicit_static_rate_exists(static_rate.target_currency, static_rate.base_currency, month_start):
            MonthlyExchangeRate.objects.update_or_create(
                effective_date=month_start,
                base_currency=static_rate.target_currency,
                target_currency=static_rate.base_currency,
                defaults={
                    "exchange_rate": inverse_rate,
                    "rate_type": RateType.STATIC,
                },
            )


def remove_static_and_backfill_dynamic(base_currency, target_currency, start_date, end_date):
    """Remove static rows for affected months and backfill with dynamic rates from ExchangeRateDictionary.

    Also removes auto-generated inverse rows unless an explicit StaticExchangeRate
    defines the reverse direction for that month.
    """
    MonthlyExchangeRate.objects.filter(
        effective_date__gte=start_date.replace(day=1),
        effective_date__lte=end_date.replace(day=1),
        base_currency=base_currency,
        target_currency=target_currency,
        rate_type=RateType.STATIC,
    ).delete()

    for month_start in _iter_months(start_date, end_date):
        if not _explicit_static_rate_exists(target_currency, base_currency, month_start):
            MonthlyExchangeRate.objects.filter(
                effective_date=month_start,
                base_currency=target_currency,
                target_currency=base_currency,
                rate_type=RateType.STATIC,
            ).delete()

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return

    exchange_dict = erd.currency_exchange_dictionary
    rate = exchange_dict.get(base_currency, {}).get(target_currency)
    if rate is not None:
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

    inverse_rate = exchange_dict.get(target_currency, {}).get(base_currency)
    if inverse_rate is not None:
        for month_start in _iter_months(start_date, end_date):
            if not _explicit_static_rate_exists(target_currency, base_currency, month_start):
                MonthlyExchangeRate.objects.update_or_create(
                    effective_date=month_start,
                    base_currency=target_currency,
                    target_currency=base_currency,
                    defaults={
                        "exchange_rate": inverse_rate,
                        "rate_type": RateType.DYNAMIC,
                    },
                )


def remove_dynamic_rates_for_currency(currency_code):
    """Remove dynamic MER rows where the disabled currency is either base or target.

    Static rows are preserved — the admin explicitly defined those and
    should remove them separately if needed.
    """
    deleted, _ = MonthlyExchangeRate.objects.filter(
        rate_type=RateType.DYNAMIC,
        base_currency=currency_code,
    ).delete()
    deleted_target, _ = MonthlyExchangeRate.objects.filter(
        rate_type=RateType.DYNAMIC,
        target_currency=currency_code,
    ).delete()
    total = deleted + deleted_target
    LOG.info(log_json(msg="Removed dynamic MER rows for disabled currency", currency=currency_code, deleted=total))
    return total


def populate_dynamic_rates_for_currency(currency_code, current_month):
    """Create dynamic MER rows for a newly enabled currency using the ExchangeRateDictionary.

    Only creates pairs where both sides are enabled. Skips pairs that
    already have a static rate for the current month.
    """
    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return 0

    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    exchange_dict = erd.currency_exchange_dictionary
    static_pairs = set(
        MonthlyExchangeRate.objects.filter(
            effective_date=current_month,
            rate_type=RateType.STATIC,
        ).values_list("base_currency", "target_currency")
    )

    created = 0
    for other_code in enabled_codes:
        if other_code == currency_code:
            continue
        for base, target in [(currency_code, other_code), (other_code, currency_code)]:
            if (base, target) in static_pairs:
                continue
            rate = exchange_dict.get(base, {}).get(target)
            if rate is not None:
                MonthlyExchangeRate.objects.update_or_create(
                    effective_date=current_month,
                    base_currency=base,
                    target_currency=target,
                    defaults={"exchange_rate": Decimal(str(rate)), "rate_type": RateType.DYNAMIC},
                )
                created += 1

    LOG.info(log_json(msg="Populated dynamic MER rows for enabled currency", currency=currency_code, created=created))
    return created
