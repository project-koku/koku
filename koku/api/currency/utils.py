#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import connection
from django.db.models import Case
from django.db.models import DecimalField
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import ExtractMonth
from django.db.models.functions import ExtractYear

from api.common import log_json
from api.currency.currencies import get_enabled_currency_codes
from api.currency.exceptions import ExchangeRateNotFound
from api.currency.models import ExchangeRateDictionary
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from api.utils import to_date
from cost_models.models import MonthlyExchangeRate
from koku.settings import KOKU_DEFAULT_CURRENCY

LOG = logging.getLogger(__name__)


def dynamic_fx_available():
    """Return True when dynamic market rates can be fetched via CURRENCY_URL."""
    return bool((settings.CURRENCY_URL or "").strip())


def restrict_enabled_currencies_for_onprem_offline(schema_name):
    """Trim seeded enablement on new on-prem tenants without dynamic FX.

    Migration 0014 seeds many currencies on every schema clone. On on-prem
    installs without ``CURRENCY_URL``, those codes are not convertible until
    static rates exist. Keep the system default and account display currency
    only (see constant-currency design).
    """
    from django_tenants.utils import schema_context

    from cost_models.models import EnabledCurrency
    from cost_models.monthly_exchange_rate_utils import remove_monthly_rates
    from koku.cache import build_enabled_currency_codes_key
    from koku.cache import delete_value_from_cache
    from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
    from reporting.user_settings.models import UserSettings

    keep = {KOKU_DEFAULT_CURRENCY}
    removed = []

    with schema_context(schema_name):
        account_settings = UserSettings.objects.first()
        if account_settings:
            account_currency = (account_settings.settings or {}).get("currency")
            if account_currency:
                keep.add(str(account_currency).upper())

        for code in keep:
            EnabledCurrency.objects.get_or_create(currency_code=code)

        removed = list(EnabledCurrency.objects.exclude(currency_code__in=keep).values_list("currency_code", flat=True))
        if not removed:
            return []

        for code in removed:
            remove_monthly_rates(code=code)
        EnabledCurrency.objects.filter(currency_code__in=removed).delete()

    delete_value_from_cache(build_enabled_currency_codes_key(schema_name))
    invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
    LOG.info(
        log_json(
            msg="Restricted enabled currencies for on-prem offline deploy",
            schema=schema_name,
            kept=sorted(keep),
            removed=removed,
        )
    )
    return removed


def _conversion_horizon_end():
    """Last month included in offline enablement coverage checks (current + next)."""
    current_month = DateHelper().this_month_start.date()
    return current_month + relativedelta(months=1)


# User-facing wording for offline coverage gaps (matches ``currency_conversion_ready`` horizon).
_OFFLINE_STATIC_COVERAGE_PERIOD = "across the retained reporting window through the next month"


def conversion_coverage(base_currency, target_currency, start_month, end_month):
    """Stable API wrapper for monthly exchange-rate conversion coverage."""
    from cost_models.monthly_exchange_rate_utils import conversion_coverage as monthly_rate_conversion_coverage

    return monthly_rate_conversion_coverage(base_currency, target_currency, start_month, end_month)


def required_targets_for_enablement():
    """Report/display targets that must be reachable when enabling offline."""
    targets = {KOKU_DEFAULT_CURRENCY}
    from reporting.user_settings.models import UserSettings

    account_settings = UserSettings.objects.first()
    if account_settings:
        account_currency = (account_settings.settings or {}).get("currency")
        if account_currency:
            targets.add(str(account_currency).upper())
    return targets


def currency_conversion_ready(code):
    """True when enabling ``code`` can succeed without dynamic market rates."""
    code = code.upper()
    if dynamic_fx_available():
        return True
    retention_start = to_date(materialized_view_month_start(schema_name=getattr(connection, "schema_name", None)))
    end_month = _conversion_horizon_end()
    for target in required_targets_for_enablement():
        if target == code:
            continue
        if not conversion_coverage(code, target, retention_start, end_month):
            return False
    return True


def enablement_blocked_detail(code):
    """Actionable 400 message when offline enable lacks static rate coverage."""
    code = code.upper()
    targets = sorted(t for t in required_targets_for_enablement() if t != code)
    target_phrase = " and ".join(targets) if targets else KOKU_DEFAULT_CURRENCY
    return (
        f"Cannot enable {code} without static exchange rates from {code} to "
        f"{target_phrase} {_OFFLINE_STATIC_COVERAGE_PERIOD}. Create static rates via "
        f"/settings/currency/static-rates/ then retry."
    )


def denomination_blocked_detail(code):
    """Actionable validation message when offline denomination coverage is missing."""
    code = code.upper()
    targets = sorted(t for t in required_targets_for_enablement() if t != code)
    target_phrase = " and ".join(targets) if targets else KOKU_DEFAULT_CURRENCY
    return (
        f"Cannot use {code} without static exchange rates from {code} to "
        f"{target_phrase} {_OFFLINE_STATIC_COVERAGE_PERIOD}. Create static rates via "
        f"/settings/currency/static-rates/ then retry."
    )


def offline_denomination_validation_detail(currency):
    """Return ``denomination_blocked_detail`` when offline static coverage is required but missing."""
    if not currency:
        return None
    code = str(currency).upper()
    if dynamic_fx_available():
        return None
    if currency_conversion_ready(code):
        return None
    return denomination_blocked_detail(code)


def build_exchange_dictionary(rates):
    """Build the exchange rates dictionary"""
    exchanged_rates = {}
    for currency_key, base_rate in rates.items():
        exchanged = {currency: Decimal(rate / base_rate) for currency, rate in rates.items()}
        exchanged_rates[currency_key] = exchanged
    return exchanged_rates


def exchange_dictionary(rates):
    """Posts exchange rates dictionary to DB"""
    exchange_data = build_exchange_dictionary(rates)
    current_data = ExchangeRateDictionary.objects.all().first()
    if not current_data:
        ExchangeRateDictionary.objects.create(currency_exchange_dictionary=exchange_data)
    else:
        current_data.currency_exchange_dictionary = exchange_data
        current_data.save()


def ensure_exchange_rate_dictionary():
    """Ensure the shared ExchangeRateDictionary has rates, fetching if needed.

    Returns True when a non-empty dictionary is available after this call.
    Does not walk tenant schemas — only fills the public ERD snapshot used as
    the source for MonthlyExchangeRate population.
    """
    erd = ExchangeRateDictionary.objects.first()
    if erd and erd.currency_exchange_dictionary:
        return True

    url = (settings.CURRENCY_URL or "").strip()
    if not url:
        LOG.info(log_json(msg="Cannot populate empty ExchangeRateDictionary; CURRENCY_URL not configured"))
        return False

    # Lazy import: masu.celery.tasks imports monthly rate helpers at module load.
    from masu.celery.tasks import _fetch_and_store_exchange_rates

    LOG.info(log_json(msg="ExchangeRateDictionary empty; fetching rates before MER populate"))
    _fetch_and_store_exchange_rates(url)
    erd = ExchangeRateDictionary.objects.first()
    return bool(erd and erd.currency_exchange_dictionary)


def build_exchange_rate_case(cost_units_key, target_currency, exchange_rates, base_currencies=None):
    """Build a Case/When annotation for flag-off currency conversion.

    Limits When clauses to enabled (or provided) base currencies that exist in
    ``exchange_rates``, so report SQL does not grow with every ISO code stored
    in ExchangeRateDictionary.

    Requires tenant schema context when ``base_currencies`` is omitted (same as
    ``get_enabled_currency_codes()``).

    Args:
        cost_units_key: ORM field name for the row's base currency column.
        target_currency: Currency code to convert to (e.g. "USD").
        exchange_rates: Nested dict from ExchangeRateDictionary
            ``{base: {target: rate, ...}, ...}``.
        base_currencies: Optional iterable of base codes. Defaults to the
            tenant's enabled currency codes.
    """
    if base_currencies is None:
        base_currencies = get_enabled_currency_codes()
    whens = [
        When(**{cost_units_key: code, "then": Value(exchange_rates.get(code, {}).get(target_currency))})
        for code in base_currencies
        if code in exchange_rates
    ]
    return Case(*whens, default=1, output_field=DecimalField())


def build_monthly_rate_annotation(base_currency, target_currency):
    """Build a Subquery annotation that resolves the exchange rate for the row's month.

    Matches the row's usage_start year/month against MonthlyExchangeRate.effective_date.
    Returns NULL for months with no MER row.

    Args:
        base_currency: the base currency to convert from (e.g. "USD")
        target_currency: the target currency to convert to (e.g. "EUR")
    """
    return Subquery(
        MonthlyExchangeRate.objects.filter(
            effective_date__year=ExtractYear(OuterRef("usage_start")),
            effective_date__month=ExtractMonth(OuterRef("usage_start")),
            base_currency=base_currency,
            target_currency=target_currency,
        ).values("exchange_rate")[:1]
    )


def get_monthly_exchange_rate(base_currency, target_currency, month_start):
    """Return the MonthlyExchangeRate for a single base/target pair and month.

    Args:
        base_currency: currency code to convert from
        target_currency: currency code to convert to
        month_start: first day of the month (date)

    Returns:
        Decimal exchange rate

    Raises:
        ExchangeRateNotFound: if no MER row exists for the pair and month
    """
    if base_currency == target_currency:
        return Decimal("1")

    month_start = month_start.replace(day=1) if hasattr(month_start, "replace") else month_start
    rate = (
        MonthlyExchangeRate.objects.filter(
            effective_date=month_start,
            base_currency=base_currency,
            target_currency=target_currency,
        )
        .values_list("exchange_rate", flat=True)
        .first()
    )
    if rate is None:
        raise ExchangeRateNotFound([base_currency], target_currency, month_start, month_start)
    return rate


def get_monthly_exchange_rate_map(base_currencies, target_currency, start_date, end_date):
    """Return monthly exchange rates for each base currency and month in range.

    The returned shape is ``{base_currency: {month_start: exchange_rate}}``.
    Identity conversions are included as ``1`` without reading
    MonthlyExchangeRate. Missing non-identity rows raise ExchangeRateNotFound.
    """
    base_currencies = set(base_currencies) - {None}
    date_helper = DateHelper()
    start_month = date_helper.month_start(start_date)
    months = [month_start for month_start, _ in date_helper.list_month_tuples(start_month, end_date)]
    rates_by_currency = {
        base: {month: Decimal("1") for month in months} for base in base_currencies if base == target_currency
    }

    bases_needing_conversion = base_currencies - {target_currency}
    if not bases_needing_conversion:
        return rates_by_currency

    end_month = months[-1]
    rates = MonthlyExchangeRate.objects.filter(
        effective_date__gte=start_month,
        effective_date__lte=end_month,
        base_currency__in=bases_needing_conversion,
        target_currency=target_currency,
    ).values_list("base_currency", "effective_date", "exchange_rate")

    for base, effective_date, exchange_rate in rates:
        rates_by_currency.setdefault(base, {})[effective_date] = exchange_rate

    missing = bases_needing_conversion - set(rates_by_currency.keys())
    if missing:
        LOG.warning(f"No exchange rates found for {missing} -> {target_currency}")
        raise ExchangeRateNotFound(list(missing), target_currency, start_month, end_month)

    expected_months = set(months)
    for base, covered_months in rates_by_currency.items():
        if base == target_currency:
            continue
        gaps = expected_months - set(covered_months.keys())
        if gaps:
            LOG.warning(f"Exchange rate gap for {base} -> {target_currency}: missing months {sorted(gaps)}")
            raise ExchangeRateNotFound([base], target_currency, start_month, end_month, missing_months=gaps)

    return rates_by_currency
