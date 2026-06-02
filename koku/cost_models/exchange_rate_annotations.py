#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Shared exchange rate annotation builders for query handlers and forecasts."""
from django.conf import settings
from django.db.models import Case
from django.db.models import DecimalField
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import When
from django.db.models.functions import Coalesce
from django.db.models.functions import ExtractMonth
from django.db.models.functions import ExtractYear
from django.db.models.functions import TruncDate
from django.db.models.lookups import LessThan
from rest_framework.exceptions import ValidationError

from cost_models.models import CostModel
from cost_models.models import MonthlyExchangeRate


class ExchangeRateNotFound(ValidationError):
    """Raised when no exchange rate exists for a required currency pair."""

    def __init__(self, target_currency, base_currencies, start_date, end_date):
        missing_pairs = ", ".join(f"{base} -> {target_currency}" for base in base_currencies)
        if settings.CURRENCY_URL:
            msg = (
                f"No exchange rate available for {missing_pairs} "
                f"for {start_date} to {end_date}. "
                "Ask your administrator to configure static exchange rates."
            )
        else:
            msg = (
                f"No exchange rate available for {missing_pairs} "
                f"for {start_date} to {end_date}. "
                "Ask your administrator to configure static exchange rates "
                "or enable dynamic exchange rates."
            )
        super().__init__({"currency": msg})


def _build_monthly_rate_annotation(base_currency, target_currency):
    """Build a Coalesce annotation that resolves exchange rates per month.

    Resolution order:
    1. Exact month match for the row's usage_start.
    2. Earliest available rate, but ONLY when usage_start predates the first
       MER row (backward-looking for pre-release history).
    3. NULL — caught by validation in _get_exchange_rates (returns 400).

    Uses ExtractYear/ExtractMonth instead of TruncMonth on OuterRef because
    Django's ResolvedOuterRef lacks the output_field that TruncMonth requires.
    """
    pair_filter = dict(base_currency=base_currency, target_currency=target_currency)

    exact_month = Subquery(
        MonthlyExchangeRate.objects.filter(
            effective_date__year=ExtractYear(OuterRef("usage_start")),
            effective_date__month=ExtractMonth(OuterRef("usage_start")),
            **pair_filter,
        ).values("exchange_rate")[:1]
    )

    earliest_qs = MonthlyExchangeRate.objects.filter(**pair_filter).order_by("effective_date")

    backward_looking = Case(
        When(
            condition=LessThan(TruncDate("usage_start"), Subquery(earliest_qs.values("effective_date")[:1])),
            then=Subquery(earliest_qs.values("exchange_rate")[:1]),
        ),
        output_field=DecimalField(),
    )

    return Coalesce(exact_month, backward_looking, output_field=DecimalField())


def build_exchange_rate_annotation_dict(cost_units_key, target_currency):
    """Build annotation dict with a single 'exchange_rate' key.

    Used by non-OCP query handlers and forecasts where there is only one
    currency dimension (the bill/report currency).
    """
    return {"exchange_rate": _build_monthly_rate_annotation(OuterRef(cost_units_key), target_currency)}


def build_ocp_exchange_rate_annotation_dict(cost_units_key, target_currency):
    """Build annotation dict with dual exchange rates for OCP.

    OCP needs two annotations:
    - exchange_rate: cost model currency (resolved via source_uuid -> CostModel.currency)
    - infra_exchange_rate: cloud bill currency (raw_currency column)
    """
    cost_model_currency = Subquery(
        CostModel.objects.filter(costmodelmap__provider_uuid=OuterRef(OuterRef("source_uuid")),).values(
            "currency"
        )[:1],
    )

    return {
        "exchange_rate": _build_monthly_rate_annotation(cost_model_currency, target_currency),
        "infra_exchange_rate": _build_monthly_rate_annotation(OuterRef(cost_units_key), target_currency),
    }
