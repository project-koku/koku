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
from django.utils import timezone
from django_tenants.utils import schema_context
from psycopg2.extras import execute_values

from api.common import log_json
from api.currency.models import ExchangeRateDictionary
from api.currency.utils import ensure_exchange_rate_dictionary
from api.iam.models import Tenant
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


def _retention_month_start():
    """First month of the tenant retention window (date), or RETAIN_NUM_MONTHS fallback."""
    return to_date(materialized_view_month_start(schema_name=getattr(connection, "schema_name", None)))


def _iter_month_starts(start_date, end_date):
    """Yield first-of-month dates from start_date through end_date inclusive."""
    month = to_date(start_date).replace(day=1)
    end = to_date(end_date).replace(day=1)
    while month <= end:
        yield month
        month += relativedelta(months=1)


def _months_in_static_window(start_date, end_date):
    """Months to materialize for a static rate: retention through the rate's end month.

    Future months inside the configured window are written immediately so the
    row exists before that month starts. Months before the retention window
    are skipped (reports cannot query them).
    """
    retention_start = _retention_month_start()
    window_start = max(to_date(start_date).replace(day=1), retention_start)
    window_end = to_date(end_date).replace(day=1)
    if window_start > window_end:
        return
    yield from _iter_month_starts(window_start, window_end)


def _open_month_starts():
    """Return the current month and the next month, the provisional dynamic horizon."""
    current_month = DateHelper().this_month_start.date()
    return current_month, current_month + relativedelta(months=1)


def _unfinalized_static_months(static_rate, current_month):
    """Yield months from max(rate start, current month) through the rate's end month.

    Past months are finalized and are not included.
    """
    window_start = max(to_date(static_rate.start_date).replace(day=1), current_month)
    window_end = to_date(static_rate.end_date).replace(day=1)
    if window_start > window_end:
        return
    yield from _iter_month_starts(window_start, window_end)


def _upsert_static_month(static_rate, month_start):
    """Write one STATIC MonthlyExchangeRate row for the given month."""
    MonthlyExchangeRate.objects.update_or_create(
        effective_date=month_start,
        base_currency=static_rate.base_currency,
        target_currency=static_rate.target_currency,
        defaults={
            "exchange_rate": static_rate.exchange_rate,
            "rate_type": RateType.STATIC,
        },
    )


def upsert_static_monthly_rates(static_rate):
    """Upsert MonthlyExchangeRate STATIC rows for each month in the rate window.

    Writes every month from max(rate.start, retention) through rate.end, including
    future months, so those rows exist before the month starts.

    The reverse direction uses dynamic rates unless the user has explicitly
    defined a StaticExchangeRate for that direction.
    """
    if Decimal(str(static_rate.exchange_rate)) <= 0:
        raise ValueError(f"exchange_rate must be positive, got {static_rate.exchange_rate}")

    for month_start in _months_in_static_window(static_rate.start_date, static_rate.end_date):
        _upsert_static_month(static_rate, month_start)


def rematerialize_current_month_static_rates(code=None, enabled_codes=None):
    """Re-apply StaticExchangeRate definitions onto unfinalized MER rows.

    Used on currency re-enable, daily crawl, and new-schema fill so surviving
    static definitions take effect when the STATIC MER row is missing (deleted
    on disable, or not yet written for a month that has not started).

    Writes each enabled definition from the current month through its end date,
    or from the definition start when that start is still in the future. Past
    months are finalized and left untouched. Only pairs where both currencies
    are enabled are written, so a disabled currency does not get its open rows
    recreated. When code is provided, only definitions involving that currency
    are applied. Forward only — reverse stays dynamic unless a reverse
    definition exists.

    Returns the number of monthly rows written (one definition covering three
    months counts as three), not the number of definitions.
    """
    if enabled_codes is None:
        enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    if not enabled_codes:
        return 0

    current_month = DateHelper().this_month_start.date()
    qs = StaticExchangeRate.objects.filter(end_date__gte=current_month)
    if code:
        qs = qs.filter(Q(base_currency=code) | Q(target_currency=code))

    rows_written = 0
    definitions = 0
    for static_rate in qs:
        if static_rate.base_currency not in enabled_codes or static_rate.target_currency not in enabled_codes:
            continue
        if Decimal(str(static_rate.exchange_rate)) <= 0:
            LOG.warning(
                log_json(
                    msg="Skipping non-positive static exchange rate during rematerialize",
                    base_currency=static_rate.base_currency,
                    target_currency=static_rate.target_currency,
                    rate=str(static_rate.exchange_rate),
                )
            )
            continue
        wrote_definition = False
        for month_start in _unfinalized_static_months(static_rate, current_month):
            _upsert_static_month(static_rate, month_start)
            rows_written += 1
            wrote_definition = True
        if wrote_definition:
            definitions += 1

    if rows_written:
        LOG.info(
            log_json(
                msg="Rematerialized unfinalized static exchange rates",
                rows=rows_written,
                definitions=definitions,
                code=code,
            )
        )
    return rows_written


def replace_static_to_dynamic_monthly_rates(base_currency, target_currency, start_date, end_date):
    """Remove static MonthlyExchangeRate rows in the window and restore dynamic rates.

    Acts on every month from max(start, retention) through the rate's end month,
    including future months. Also removes any stale inverse static row unless an
    explicit StaticExchangeRate defines the reverse direction for that month.

    After removing static overrides, repopulates dynamic rates for the current
    month and the next month from ExchangeRateDictionary, and backfills missing
    past months with the next later MER rate for the pair (same rule as the daily
    crawl). Does not write today's ERD rate into closed months, and does not
    invent dynamic rows past the next month. Existing non-static monthly rows
    are left unchanged.
    """
    months = list(_months_in_static_window(start_date, end_date))
    if not months:
        return

    for month_start in months:
        MonthlyExchangeRate.objects.filter(
            effective_date=month_start,
            base_currency=base_currency,
            target_currency=target_currency,
            rate_type=RateType.STATIC,
        ).delete()

        if not _explicit_static_rate_exists(target_currency, base_currency, month_start):
            MonthlyExchangeRate.objects.filter(
                effective_date=month_start,
                base_currency=target_currency,
                target_currency=base_currency,
                rate_type=RateType.STATIC,
            ).delete()

    # Current and next month from ERD; past gaps inherit the next later MER for the pair.
    populate_dynamic_monthly_rates(code=base_currency, backfill_past_months=True)


def populate_monthly_rates_for_schema(schema_name):
    """Populate dynamic monthly rates for one tenant schema from the shared dictionary.

    ``template0`` is cloned with ``copy_data`` and does not carry a current market
    snapshot on a fresh database. Call this after the clone commits so the new
    schema can convert costs without waiting for the daily currency beat.
    If ``ExchangeRateDictionary`` is empty, fetch rates first (when
    ``CURRENCY_URL`` is set) before writing MER. Current-month and next-month
    rows are upserted and missing months in the retention window are
    backfilled, matching ``get_daily_currency_rates``.
    """
    ensure_exchange_rate_dictionary()
    with schema_context(schema_name):
        updated = populate_dynamic_monthly_rates(backfill_past_months=True)
    LOG.info(
        log_json(
            msg="Populated monthly exchange rates for schema",
            schema=schema_name,
            updated=updated,
        )
    )
    return updated


def _rates_from_exchange_dictionary(exchange_dict, enabled_codes, code=None):
    """Return enabled pair rates from the market snapshot, with synthesized inverses.

    ``{(base, target): Decimal}``. An explicit reverse entry in the dictionary
    wins over ``1/rate``. Non-positive rates are skipped.
    """
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


def _static_pairs_by_month(months):
    """Return ``{month: {(base, target)}}`` for STATIC rows in ``months``.

    The caller passes only the months it is about to write. Today that is the
    current month and the next month.
    """
    pairs = {}
    rows = MonthlyExchangeRate.objects.filter(
        effective_date__in=months,
        rate_type=RateType.STATIC,
    ).values_list("effective_date", "base_currency", "target_currency")
    for effective_date, base_cur, target_cur in rows:
        pairs.setdefault(effective_date, set()).add((base_cur, target_cur))
    return pairs


def _upsert_dynamic_rates(dynamic_rates, months):
    """Bulk-upsert DYNAMIC rows for each month, skipping pairs that are STATIC that month.

    Returns the number of rows submitted. One statement per call, conflict
    target ``(base_currency, target_currency, effective_date)``.

    The pre-filter skips known STATIC pairs. A STATIC row created after that
    read still wins: the conflict update does not change ``rate_type`` and
    does not run when the stored row is already static, so neither the type
    nor the static rate is replaced.
    """
    if not dynamic_rates or not months:
        return 0

    static_pairs = _static_pairs_by_month(months)
    now = timezone.now()
    values = []
    for month_start in months:
        blocked = static_pairs.get(month_start, ())
        for (base_cur, target_cur), rate in dynamic_rates.items():
            if (base_cur, target_cur) in blocked:
                continue
            values.append((month_start, base_cur, target_cur, rate, RateType.DYNAMIC, now, now))
    if not values:
        return 0

    table = connection.ops.quote_name(MonthlyExchangeRate._meta.db_table)
    # rate_type is inserted for new rows and omitted from the update, so a
    # conflict cannot relabel a row. The WHERE keeps a concurrent STATIC row's
    # exchange_rate as well.
    sql = f"""
        INSERT INTO {table} (
            effective_date,
            base_currency,
            target_currency,
            exchange_rate,
            rate_type,
            created_timestamp,
            updated_timestamp
        )
        VALUES %s
        ON CONFLICT (base_currency, target_currency, effective_date)
        DO UPDATE SET
            exchange_rate = EXCLUDED.exchange_rate,
            updated_timestamp = EXCLUDED.updated_timestamp
        WHERE {table}.rate_type <> '{RateType.STATIC}'
    """
    with connection.cursor() as cursor:
        execute_values(cursor, sql, values)
    return len(values)


def populate_dynamic_monthly_rates(code=None, backfill_past_months=False):
    """Populate dynamic MonthlyExchangeRate rows for the current month and the next.

    Past months are finalized and read-only. The next month is a provisional
    snapshot of the latest ExchangeRateDictionary, refreshed on every run, so
    the row exists before that month starts. Closed months are never overwritten.

    When backfill_past_months is True (daily currency task, or a new tenant
    schema), each missing month in the retention window is filled from the next
    later existing MonthlyExchangeRate for that pair. The provisional next month
    is not a backfill source and is not copied backward.

    First rematerializes STATIC rows from the current month through each
    definition's end date. Then writes dynamic rows for remaining enabled
    currency pairs. Static overrides are preserved per month. If ERD is
    missing or empty and backfill_past_months is True, still backfill from
    existing MER.

    When code is provided, only pairs involving that currency are processed.
    When None, all enabled currency pairs are processed.
    """
    enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
    if not enabled_codes:
        LOG.warning(log_json(msg="No enabled currencies; skipping monthly exchange rate populate"))
        return 0

    current_month, next_month = _open_month_starts()
    updated_count = rematerialize_current_month_static_rates(code=code, enabled_codes=enabled_codes)
    erd = ExchangeRateDictionary.objects.first()
    if erd and erd.currency_exchange_dictionary:
        dynamic_rates = _rates_from_exchange_dictionary(erd.currency_exchange_dictionary, enabled_codes, code=code)
        updated_count += _upsert_dynamic_rates(dynamic_rates, (current_month, next_month))

    backfilled_count = 0
    if backfill_past_months:
        backfilled_count = _backfill_missing_past_months(current_month, enabled_codes=enabled_codes, code=code)

    return updated_count + backfilled_count


def remove_monthly_rates(code):
    """Remove MonthlyExchangeRate rows involving the currency from the current month forward.

    Past months are finalized and read-only. The current month and any provisional
    future rows are removed so a disabled currency does not become convertible
    again when the next month starts.
    """
    current_month = DateHelper().this_month_start.date()
    deleted, _ = (
        MonthlyExchangeRate.objects.filter(effective_date__gte=current_month)
        .filter(Q(base_currency=code) | Q(target_currency=code))
        .delete()
    )
    LOG.info(log_json(msg="Removed MonthlyExchangeRate rows", code=code, deleted=deleted))
    return deleted


def _purge_expired_monthly_rates(simulate=False):
    """Delete MonthlyExchangeRate rows older than the retention window.

    Uses the same retention boundary as backfill (materialized_view_month_start).
    Must be called within a schema_context.
    """
    expired_date = to_date(materialized_view_month_start(schema_name=connection.schema_name))
    query = MonthlyExchangeRate.objects.filter(effective_date__lt=expired_date)
    if simulate:
        deleted = query.count()
    else:
        deleted, _ = query.delete()
    if deleted:
        LOG.info(
            log_json(
                msg="Purged expired MonthlyExchangeRate rows",
                simulate=simulate,
                deleted=deleted,
                expired_date=str(expired_date),
            )
        )
    return deleted


def purge_expired_exchange_rates_for_all_tenants(simulate=False):
    """Purge expired MonthlyExchangeRate rows for all tenants."""
    for tenant in Tenant.objects.exclude(schema_name="public"):
        try:
            with schema_context(tenant.schema_name):
                _purge_expired_monthly_rates(simulate=simulate)
        except Exception as e:
            LOG.error(
                log_json(
                    msg="Failed to purge expired monthly exchange rates",
                    schema=tenant.schema_name,
                    error=str(e),
                )
            )


def _get_existing_rates_by_pair(start, end, enabled_codes, code=None):
    """Return existing MER rates grouped by pair, ordered newest-first.

    {("USD", "EUR"): {date(2026, 6, 1): Decimal("0.45"), date(2026, 4, 1): Decimal("0.40")}}

    Dict insertion order is newest-first, so next(iter(d.items())) gives the latest rate.
    """
    qs = MonthlyExchangeRate.objects.filter(
        base_currency__in=enabled_codes,
        target_currency__in=enabled_codes,
        effective_date__gte=start,
        effective_date__lte=end,
    )
    if code:
        qs = qs.filter(Q(base_currency=code) | Q(target_currency=code))

    rates_by_pair = {}
    for base, target, effective, rate in qs.order_by(
        "base_currency", "target_currency", "-effective_date"
    ).values_list("base_currency", "target_currency", "effective_date", "exchange_rate"):
        rates_by_pair.setdefault((base, target), {})[effective] = rate

    return rates_by_pair


def _backfill_missing_past_months(current_month, enabled_codes, code=None):
    """Fill gaps walking downward; each missing month inherits the next later rate.

    Example (Jan–Jun, rows at Apr/Jun): May<-Jun, Mar<-Apr, Feb<-Apr, Jan<-Apr.

    Discovers pairs from existing MER rows in the retention window.
    Returns the number of rows created.
    """
    retention_start = to_date(materialized_view_month_start(schema_name=getattr(connection, "schema_name", None)))
    if retention_start >= current_month:
        LOG.warning(
            log_json(
                msg="Skipping MER backfill; retention start is at or after current month",
                retention_start=str(retention_start),
                current_month=str(current_month),
            )
        )
        return 0

    rates_by_pair = _get_existing_rates_by_pair(retention_start, current_month, enabled_codes=enabled_codes, code=code)

    if not rates_by_pair:
        return 0

    rows_to_create = []
    for (base, target), existing_rates in rates_by_pair.items():
        # First entry is the latest because the query is ordered newest-first.
        most_recent_month, fill_rate = next(iter(existing_rates.items()))
        current_fill_month = most_recent_month - relativedelta(months=1)
        while current_fill_month >= retention_start:
            if current_fill_month in existing_rates:
                fill_rate = existing_rates[current_fill_month]
            else:
                rows_to_create.append(
                    MonthlyExchangeRate(
                        effective_date=current_fill_month,
                        base_currency=base,
                        target_currency=target,
                        exchange_rate=fill_rate,
                        rate_type=RateType.DYNAMIC,
                    )
                )
            current_fill_month -= relativedelta(months=1)

    if rows_to_create:
        MonthlyExchangeRate.objects.bulk_create(rows_to_create, ignore_conflicts=True)
        LOG.info(log_json(msg="Backfilled missing monthly exchange rates", created=len(rows_to_create)))

    return len(rows_to_create)
