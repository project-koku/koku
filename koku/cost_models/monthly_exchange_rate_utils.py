#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utilities for managing MonthlyExchangeRate side effects."""
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Q

from api.common import log_json
from api.currency.models import ExchangeRateDictionary
from api.utils import DateHelper
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
    """Remove static rows for affected months and backfill with dynamic rates.

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
        populate_dynamic_monthly_rates(code=base_currency, month=month_start)


def populate_dynamic_monthly_rates(code=None, month=None):
    """Populate dynamic MonthlyExchangeRate rows for enabled currencies.

    Reads the latest rates from ExchangeRateDictionary and writes dynamic
    MonthlyExchangeRate rows for each enabled currency pair. Static overrides are preserved.

    When code is provided, only pairs involving that currency are processed.
    When None, all enabled currency pairs are processed.

    When month is provided, writes for that specific month.
    When None, defaults to the current month.
    """
    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    if not enabled_codes:
        return 0

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return 0

    exchange_dict = erd.currency_exchange_dictionary
    current_month = month or DateHelper().this_month_start.date()

    static_pairs = set(
        MonthlyExchangeRate.objects.filter(
            effective_date=current_month,
            rate_type=RateType.STATIC,
        ).values_list("base_currency", "target_currency")
    )

    candidates = {}
    for base_cur, targets in exchange_dict.items():
        for target_cur, rate in targets.items():
            if base_cur == target_cur:
                continue
            if base_cur not in enabled_codes or target_cur not in enabled_codes:
                continue
            if code and code not in (base_cur, target_cur):
                continue
            candidates[(base_cur, target_cur)] = Decimal(str(rate))
            candidates.setdefault((target_cur, base_cur), Decimal(1) / Decimal(str(rate)))

    pairs_to_upsert = {pair: rate for pair, rate in candidates.items() if pair not in static_pairs}

    count = 0
    for (base_cur, target_cur), rate in pairs_to_upsert.items():
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=current_month,
            base_currency=base_cur,
            target_currency=target_cur,
            defaults={"exchange_rate": rate, "rate_type": RateType.DYNAMIC},
        )
        count += 1

    return count


def remove_dynamic_monthly_rates(code):
    """Remove dynamic MonthlyExchangeRate rows involving the given currency.

    Static rows are always preserved.
    """
    deleted, _ = (
        MonthlyExchangeRate.objects.filter(rate_type=RateType.DYNAMIC)
        .filter(Q(base_currency=code) | Q(target_currency=code))
        .delete()
    )
    LOG.info(log_json(msg="Removed dynamic MonthlyExchangeRate rows", code=code, deleted=deleted))
    return deleted
