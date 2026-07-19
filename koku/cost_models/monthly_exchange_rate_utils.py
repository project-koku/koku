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
    If ERD is missing/empty and backfill_past_months is True, still backfill from existing MER.

    When code is provided, only pairs involving that currency are processed.
    When None, all enabled currency pairs are processed.
    """
    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    if not enabled_codes:
        LOG.warning(log_json(msg="No enabled currencies; skipping monthly exchange rate populate"))
        return

    current_month = DateHelper().this_month_start.date()
    erd = ExchangeRateDictionary.objects.first()
    if erd and erd.currency_exchange_dictionary:
        exchange_dict = erd.currency_exchange_dictionary

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
                inverse_rate = Decimal(1) / rate_dec
                dynamic_rates[forward_pair] = rate_dec
                dynamic_rates.setdefault(inverse_pair, inverse_rate)

        # Exclude pairs that already have a static override for this month
        pairs_to_upsert = {pair: rate for pair, rate in dynamic_rates.items() if pair not in static_pairs}

        for (base_cur, target_cur), rate in pairs_to_upsert.items():
            MonthlyExchangeRate.objects.update_or_create(
                effective_date=current_month,
                base_currency=base_cur,
                target_currency=target_cur,
                defaults={"exchange_rate": rate, "rate_type": RateType.DYNAMIC},
            )

    if backfill_past_months:
        _backfill_missing_past_months(current_month, code=code)


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


def _backfill_missing_past_months(current_month, code=None):
    """Fill gaps walking downward; each missing month inherits the next later rate.

    Example (Jan–Jun, rows at Apr/Jun): May<-Jun, Mar<-Apr, Feb<-Apr, Jan<-Apr.

    Discovers pairs from existing MER rows in the retention window.
    """
    start = to_date(materialized_view_month_start(schema_name=getattr(connection, "schema_name", None)))
    if start >= current_month:
        LOG.warning(
            log_json(
                msg="Skipping MER backfill; retention start is at or after current month",
                retention_start=str(start),
                current_month=str(current_month),
            )
        )
        return

    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    rates_qs = MonthlyExchangeRate.objects.filter(
        base_currency__in=enabled_codes,
        target_currency__in=enabled_codes,
        effective_date__gte=start,
        effective_date__lte=current_month,
    )
    if code:
        rates_qs = rates_qs.filter(Q(base_currency=code) | Q(target_currency=code))

    # {("USD", "EUR"): {date(2026, 4, 1): Decimal("0.40"), date(2026, 6, 1): Decimal("0.45")}}
    rates_by_pair = {}
    for base, target, effective, rate in rates_qs.values_list(
        "base_currency", "target_currency", "effective_date", "exchange_rate"
    ):
        rates_by_pair.setdefault((base, target), {})[effective] = rate

    if not rates_by_pair:
        return

    to_create = []
    for (base, target), existing in rates_by_pair.items():
        # Walk down from the month before the latest available MER row.
        latest_month = max(existing)
        latest_rate = existing[latest_month]
        month = latest_month - relativedelta(months=1)
        while month >= start:
            if month in existing:
                latest_rate = existing[month]
            else:
                to_create.append(
                    MonthlyExchangeRate(
                        effective_date=month,
                        base_currency=base,
                        target_currency=target,
                        exchange_rate=latest_rate,
                        rate_type=RateType.DYNAMIC,
                    )
                )
            month -= relativedelta(months=1)

    if to_create:
        MonthlyExchangeRate.objects.bulk_create(to_create, ignore_conflicts=True)
        LOG.info(log_json(msg="Backfilled missing monthly exchange rates", created=len(to_create)))
