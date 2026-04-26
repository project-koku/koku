#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utilities for managing MonthlyExchangeRate side effects of StaticExchangeRate operations."""
from dateutil.relativedelta import relativedelta

from api.currency.models import ExchangeRateDictionary
from cost_models.models import CurrencyConfig
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType


def iter_months(start_date, end_date):
    """Yield the first day of each month between start_date and end_date inclusive."""
    current = start_date.replace(day=1)
    end = end_date.replace(day=1)
    while current <= end:
        yield current
        current += relativedelta(months=1)


def ensure_currencies_enabled(*currency_codes):
    """Ensure CurrencyConfig rows exist and are enabled for the given currency codes."""
    for code in currency_codes:
        CurrencyConfig.objects.update_or_create(
            currency_code=code,
            defaults={"enabled": True},
        )


def upsert_static_monthly_rates(static_rate):
    """Upsert MonthlyExchangeRate rows with rate_type=static for each month in the validity period."""
    for month_start in iter_months(static_rate.start_date, static_rate.end_date):
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=month_start,
            base_currency=static_rate.base_currency,
            target_currency=static_rate.target_currency,
            defaults={
                "exchange_rate": static_rate.exchange_rate,
                "rate_type": RateType.STATIC,
            },
        )


def remove_static_and_backfill_dynamic(base_currency, target_currency, start_date, end_date):
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

    for month_start in iter_months(start_date, end_date):
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=month_start,
            base_currency=base_currency,
            target_currency=target_currency,
            defaults={
                "exchange_rate": rate,
                "rate_type": RateType.DYNAMIC,
            },
        )
