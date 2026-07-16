#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utilities for managing MonthlyExchangeRate side effects."""
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db.models import Q

from api.common import log_json
from api.currency.models import ExchangeRateDictionary
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate

LOG = logging.getLogger(__name__)


def _explicit_static_rate_exists(base_currency, target_currency, month_start):
    """Check if a StaticExchangeRate explicitly defines this direction covering the given month."""
    return StaticExchangeRate.objects.filter(
        base_currency=base_currency,
        target_currency=target_currency,
        start_date__lte=month_start,
        end_date__gte=month_start,
    ).exists()


def upsert_static_monthly_rates(static_rate):
    """Upsert a MonthlyExchangeRate row for the current month.

    Only writes if the current month falls within the static rate's date range.
    Past and future months are not touched — each month is populated when it becomes current.

    The reverse direction uses dynamic rates unless the user has explicitly
    defined a StaticExchangeRate for that direction. If no MonthlyExchangeRate row
    exists for the inverse pair, dynamic rates are backfilled from ExchangeRateDictionary.
    """
    if static_rate.exchange_rate <= 0:
        raise ValueError(f"exchange_rate must be positive, got {static_rate.exchange_rate}")

    current_month = DateHelper().this_month_start.date()
    if current_month < static_rate.start_date or current_month > static_rate.end_date:
        return

    MonthlyExchangeRate.objects.update_or_create(
        effective_date=current_month,
        base_currency=static_rate.base_currency,
        target_currency=static_rate.target_currency,
        defaults={
            "exchange_rate": static_rate.exchange_rate,
            "rate_type": RateType.STATIC,
        },
    )


def replace_static_to_dynamic_monthly_rates(base_currency, target_currency, start_date, end_date):
    """Remove static MonthlyExchangeRate rows for the current month and backfill with dynamic rates.

    Only acts if the current month falls within the given date range.
    Past and future months are not touched — past months are finalized and read-only.
    Also removes any stale inverse static row unless an explicit StaticExchangeRate
    defines the reverse direction for this month.
    """
    current_month = DateHelper().this_month_start.date()
    if current_month < start_date or current_month > end_date:
        return

    MonthlyExchangeRate.objects.filter(
        effective_date=current_month,
        base_currency=base_currency,
        target_currency=target_currency,
        rate_type=RateType.STATIC,
    ).delete()

    if not _explicit_static_rate_exists(target_currency, base_currency, current_month):
        MonthlyExchangeRate.objects.filter(
            effective_date=current_month,
            base_currency=target_currency,
            target_currency=base_currency,
            rate_type=RateType.STATIC,
        ).delete()

    populate_dynamic_monthly_rates(code=base_currency)


def _retention_months_before_current(current_month):
    """Return month-start dates in the tenant retention window before the current month.

    Uses the same retention window as data purge (per-tenant when available).
    """
    schema_name = getattr(connection, "schema_name", None)
    earliest = materialized_view_month_start(schema_name=schema_name)
    if hasattr(earliest, "date"):
        earliest = earliest.date()

    months = []
    month = earliest
    while month < current_month:
        months.append(month)
        month += relativedelta(months=1)
    return months


def _collect_dynamic_rates(exchange_dict, enabled_codes, code=None):
    """Build enabled currency-pair rates from ExchangeRateDictionary, with inverses."""
    dynamic_rates = {}
    for base_cur, rates_by_target in exchange_dict.items():
        for target_cur, rate in rates_by_target.items():
            if base_cur == target_cur:
                continue
            if base_cur not in enabled_codes or target_cur not in enabled_codes:
                continue
            if code and code != base_cur and code != target_cur:
                continue

            rate_dec = Decimal(str(rate))
            if rate_dec <= 0:
                LOG.warning(
                    log_json(
                        msg="Skipping non-positive rate from ExchangeRateDictionary",
                        base_currency=base_cur,
                        target_currency=target_cur,
                        rate=str(rate),
                    )
                )
                continue
            dynamic_rates[(base_cur, target_cur)] = rate_dec
            dynamic_rates.setdefault((target_cur, base_cur), Decimal(1) / rate_dec)
    return dynamic_rates


def _backfill_missing_past_months(dynamic_rates, past_months):
    """Insert today's rate for any missing MonthlyExchangeRate rows in past months.

    Existing rows (static or dynamic) are never overwritten.
    """
    if not dynamic_rates or not past_months:
        return

    existing = set(
        MonthlyExchangeRate.objects.filter(
            effective_date__gte=past_months[0],
            effective_date__lte=past_months[-1],
        ).values_list("base_currency", "target_currency", "effective_date")
    )

    to_create = [
        MonthlyExchangeRate(
            effective_date=month,
            base_currency=base_cur,
            target_currency=target_cur,
            exchange_rate=rate,
            rate_type=RateType.DYNAMIC,
        )
        for (base_cur, target_cur), rate in dynamic_rates.items()
        for month in past_months
        if (base_cur, target_cur, month) not in existing
    ]
    if not to_create:
        return

    MonthlyExchangeRate.objects.bulk_create(to_create, ignore_conflicts=True)
    LOG.info(
        log_json(
            msg="Backfilled missing monthly exchange rates for retention window",
            created=len(to_create),
            months=len(past_months),
        )
    )


def populate_dynamic_monthly_rates(code=None, backfill_past_months=False):
    """Populate dynamic MonthlyExchangeRate rows for the current month.

    Current month: upserted from ExchangeRateDictionary (daily refresh). Static
    overrides for the current month are preserved.

    When backfill_past_months is True, also insert
    today's rate for any missing MonthlyExchangeRate rows in past months within
    the tenant retention window. Existing rows (static or dynamic) are never
    overwritten.

    When code is provided, only pairs involving that currency are processed.
    When None, all enabled currency pairs are processed.
    """
    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    if not enabled_codes:
        return

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return

    current_month = DateHelper().this_month_start.date()
    dynamic_rates = _collect_dynamic_rates(erd.currency_exchange_dictionary, enabled_codes, code)

    static_pairs = set(
        MonthlyExchangeRate.objects.filter(
            effective_date=current_month,
            rate_type=RateType.STATIC,
        ).values_list("base_currency", "target_currency")
    )

    for (base_cur, target_cur), rate in dynamic_rates.items():
        if (base_cur, target_cur) in static_pairs:
            continue
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=current_month,
            base_currency=base_cur,
            target_currency=target_cur,
            defaults={"exchange_rate": rate, "rate_type": RateType.DYNAMIC},
        )

    if backfill_past_months:
        _backfill_missing_past_months(dynamic_rates, _retention_months_before_current(current_month))


def remove_monthly_rates(code):
    """Remove all MonthlyExchangeRate rows (dynamic and static) involving the given currency for the current month.

    Past months are finalized and read-only — only the current month is touched.
    """
    current_month = DateHelper().this_month_start.date()
    deleted, _ = (
        MonthlyExchangeRate.objects.filter(effective_date=current_month)
        .filter(Q(base_currency=code) | Q(target_currency=code))
        .delete()
    )
    LOG.info(log_json(msg="Removed MonthlyExchangeRate rows", code=code, deleted=deleted))
    return deleted
