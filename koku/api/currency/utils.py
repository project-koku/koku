#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Case
from django.db.models import DecimalField
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import ExtractMonth
from django.db.models.functions import ExtractYear

from api.currency.currencies import get_enabled_currency_codes
from api.currency.exceptions import ExchangeRateNotFound
from api.currency.models import ExchangeRateDictionary
from cost_models.models import MonthlyExchangeRate

LOG = logging.getLogger(__name__)


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


def validate_exchange_rate_coverage(base_currencies, target_currency, start_date, end_date):
    """Check that MonthlyExchangeRate rows exist for every base currency and every month in the range.

    Raises ExchangeRateNotFound if:
    - A base currency is completely missing from MER
    - A base currency has rates for some months but not all months in the range
    """
    bases_needing_conversion = base_currencies - {target_currency}
    if not bases_needing_conversion:
        return

    start_month = start_date.replace(day=1) if hasattr(start_date, "replace") else start_date
    end_month = end_date.replace(day=1) if hasattr(end_date, "replace") else end_date

    rates = MonthlyExchangeRate.objects.filter(
        effective_date__gte=start_month,
        effective_date__lte=end_month,
        base_currency__in=bases_needing_conversion,
        target_currency=target_currency,
    ).values_list("base_currency", "effective_date")

    covered_by_currency = {}
    for base, effective_date in rates:
        covered_by_currency.setdefault(base, set()).add(effective_date)

    missing = bases_needing_conversion - set(covered_by_currency.keys())
    if missing:
        LOG.warning(f"No exchange rates found for {missing} -> {target_currency}")
        raise ExchangeRateNotFound(list(missing), target_currency, start_month, end_month)

    expected_months = set()
    current = start_month
    while current <= end_month:
        expected_months.add(current)
        current += relativedelta(months=1)

    for base, covered_months in covered_by_currency.items():
        gaps = expected_months - covered_months
        if gaps:
            LOG.warning(f"Exchange rate gap for {base} -> {target_currency}: missing months {sorted(gaps)}")
            raise ExchangeRateNotFound([base], target_currency, start_month, end_month, missing_months=gaps)
