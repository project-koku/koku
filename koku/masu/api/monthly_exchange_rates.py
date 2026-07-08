#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Admin endpoint to inspect MonthlyExchangeRate rows."""
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from cost_models.models import MonthlyExchangeRate


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def monthly_exchange_rates(request):
    """Return stored MonthlyExchangeRate rows, optionally filtered by date range and currency pair.

    Query parameters:
        start_date  - filter effective_date >= (YYYY-MM-DD, default: no lower bound)
        end_date    - filter effective_date <= (YYYY-MM-DD, default: no upper bound)
        base_currency   - filter by base currency code
        target_currency - filter by target currency code
    """
    filters = {}
    if start := request.query_params.get("start_date"):
        filters["effective_date__gte"] = start
    if end := request.query_params.get("end_date"):
        filters["effective_date__lte"] = end
    if base := request.query_params.get("base_currency"):
        filters["base_currency"] = base.upper()
    if target := request.query_params.get("target_currency"):
        filters["target_currency"] = target.upper()

    rates = list(
        MonthlyExchangeRate.objects.filter(**filters)
        .order_by("base_currency", "target_currency", "effective_date")
        .values("effective_date", "base_currency", "target_currency", "exchange_rate", "rate_type")
    )

    return Response({"count": len(rates), "rates": rates})
