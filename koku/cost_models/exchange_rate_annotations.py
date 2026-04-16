#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Shared exchange rate annotation builders for query handlers and forecasts."""
from django.db.models import DecimalField
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.db.models.functions import ExtractMonth
from django.db.models.functions import ExtractYear

from cost_models.models import CostModel
from cost_models.models import MonthlyExchangeRate


def build_monthly_rate_annotation(cost_units_key, target_currency):
    """Build a Coalesce annotation that resolves exchange rates per month.

    Tries the rate matching the row's usage_start month first, then falls back
    to the earliest available rate for the currency pair.

    Uses ExtractYear/ExtractMonth instead of TruncMonth on OuterRef because
    Django's ResolvedOuterRef lacks the output_field attribute that TruncMonth
    requires for date truncation.

    Args:
        cost_units_key: The field name on the outer query holding the base currency code.
        target_currency: The target currency code string.

    Returns:
        A Coalesce expression suitable for use in an .annotate() call.
    """
    rate_subquery = MonthlyExchangeRate.objects.filter(
        effective_date__year=ExtractYear(OuterRef("usage_start")),
        effective_date__month=ExtractMonth(OuterRef("usage_start")),
        base_currency=OuterRef(cost_units_key),
        target_currency=target_currency,
    ).values("exchange_rate")[:1]

    earliest_rate_subquery = (
        MonthlyExchangeRate.objects.filter(
            base_currency=OuterRef(cost_units_key),
            target_currency=target_currency,
        )
        .order_by("effective_date")
        .values("exchange_rate")[:1]
    )

    return Coalesce(
        Subquery(rate_subquery),
        Subquery(earliest_rate_subquery),
        output_field=DecimalField(),
    )


def build_exchange_rate_annotation_dict(cost_units_key, target_currency):
    """Build annotation dict with a single 'exchange_rate' key.

    Used by non-OCP query handlers and forecasts where there is only one
    currency dimension (the bill/report currency).
    """
    return {"exchange_rate": build_monthly_rate_annotation(cost_units_key, target_currency)}


def build_ocp_exchange_rate_annotation_dict(cost_units_key, target_currency):
    """Build annotation dict with dual exchange rates for OCP.

    OCP needs two annotations:
    - exchange_rate: cost model currency (resolved via source_uuid -> CostModel.currency)
    - infra_exchange_rate: cloud bill currency (raw_currency column)
    """
    cost_model_currency = CostModel.objects.filter(
        costmodelmap__provider_uuid=OuterRef(OuterRef("source_uuid")),
    ).values("currency")[:1]

    exchange_rate_subquery = MonthlyExchangeRate.objects.filter(
        effective_date__year=ExtractYear(OuterRef("usage_start")),
        effective_date__month=ExtractMonth(OuterRef("usage_start")),
        base_currency=Subquery(cost_model_currency),
        target_currency=target_currency,
    ).values("exchange_rate")[:1]

    earliest_exchange_rate_subquery = (
        MonthlyExchangeRate.objects.filter(
            base_currency=Subquery(cost_model_currency),
            target_currency=target_currency,
        )
        .order_by("effective_date")
        .values("exchange_rate")[:1]
    )

    return {
        "exchange_rate": Coalesce(
            Subquery(exchange_rate_subquery),
            Subquery(earliest_exchange_rate_subquery),
            output_field=DecimalField(),
        ),
        "infra_exchange_rate": build_monthly_rate_annotation(cost_units_key, target_currency),
    }
