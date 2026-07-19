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
from api.utils import to_date
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


def populate_dynamic_monthly_rates(code=None, backfill_past_months=False):  # noqa: C901
    """Populate dynamic MonthlyExchangeRate rows for the current month only.

    Past months are finalized and read-only — only the current month is written,
    unless backfill_past_months is True (daily Celery crawl), in which case each
    missing month in the retention window is filled from the next later existing
    MonthlyExchangeRate for that pair. Existing rows are never overwritten.

    Reads the latest rates from ExchangeRateDictionary and writes dynamic
    MonthlyExchangeRate rows for each enabled currency pair. Static overrides are preserved.

    When code is provided, only pairs involving that currency are processed.
    When None, all enabled currency pairs are processed.
    """
    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    if not enabled_codes:
        return 0

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return 0

    exchange_dict = erd.currency_exchange_dictionary
    current_month = DateHelper().this_month_start.date()

    static_pairs = set(
        MonthlyExchangeRate.objects.filter(
            effective_date=current_month,
            rate_type=RateType.STATIC,
        ).values_list("base_currency", "target_currency")
    )

    # Collect rates and synthesize inverses when not already in the dictionary
    dynamic_rates = {}
    for base_cur, rates_by_target in exchange_dict.items():
        for target_cur, rate in rates_by_target.items():
            if base_cur == target_cur:
                continue
            if base_cur not in enabled_codes or target_cur not in enabled_codes:
                continue
            if code and code != base_cur and code != target_cur:
                continue

            forward_pair = (base_cur, target_cur)
            inverse_pair = (target_cur, base_cur)

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
            dynamic_rates[forward_pair] = rate_dec
            dynamic_rates.setdefault(inverse_pair, Decimal(1) / rate_dec)

    # Exclude pairs that already have a static override for this month
    pairs_to_upsert = {pair: rate for pair, rate in dynamic_rates.items() if pair not in static_pairs}

    count = 0
    for (base_cur, target_cur), rate in pairs_to_upsert.items():
        MonthlyExchangeRate.objects.update_or_create(
            effective_date=current_month,
            base_currency=base_cur,
            target_currency=target_cur,
            defaults={"exchange_rate": rate, "rate_type": RateType.DYNAMIC},
        )
        count += 1

    if backfill_past_months:
        _backfill_missing_past_months(dynamic_rates.keys(), current_month)

    return count


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


def _mer_rates_by_pair(currency_pairs):
    """Return {pair: [(effective_date, rate), ...]} ordered by effective_date."""
    rates = {}
    for base, target, effective, rate in (
        MonthlyExchangeRate.objects.filter(
            base_currency__in={b for b, _ in currency_pairs},
            target_currency__in={t for _, t in currency_pairs},
        )
        .order_by("effective_date")
        .values_list("base_currency", "target_currency", "effective_date", "exchange_rate")
    ):
        if (base, target) in currency_pairs:
            rates.setdefault((base, target), []).append((effective, rate))
    return rates


def _backfill_missing_past_months(currency_pairs, current_month):
    """Fill gaps with the next later MER rate (e.g. 1<-2, 3<-4, 5<-6)."""
    pairs = set(currency_pairs)
    cursor_start = to_date(materialized_view_month_start(schema_name=getattr(connection, "schema_name", None)))
    if not pairs or cursor_start >= current_month:
        return

    to_create = []
    for (base, target), dated_rates in _mer_rates_by_pair(pairs).items():
        cursor = cursor_start
        for effective, rate in dated_rates:
            # Months before this existing row inherit its rate.
            while cursor < effective and cursor < current_month:
                to_create.append(
                    MonthlyExchangeRate(
                        effective_date=cursor,
                        base_currency=base,
                        target_currency=target,
                        exchange_rate=rate,
                        rate_type=RateType.DYNAMIC,
                    )
                )
                cursor += relativedelta(months=1)
            # Skip the existing month itself.
            if cursor == effective:
                cursor += relativedelta(months=1)

    if to_create:
        MonthlyExchangeRate.objects.bulk_create(to_create, ignore_conflicts=True)
        LOG.info(log_json(msg="Backfilled missing monthly exchange rates", created=len(to_create)))
