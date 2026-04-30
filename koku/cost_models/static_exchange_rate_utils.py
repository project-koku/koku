#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utilities for managing MonthlyExchangeRate side effects of StaticExchangeRate operations."""
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from api.currency.models import ExchangeRateDictionary
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate


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
