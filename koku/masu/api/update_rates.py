#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.celery.tasks import get_daily_currency_rates
from masu.celery.tasks import scrape_azure_storage_capacities


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def update_exchange_rates(request):
    """Return updated exchange rates."""
    exchange_result = get_daily_currency_rates()
    return Response({"updated_exchange_rates": exchange_result})


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def update_azure_storage_capacity(request):
    """Return updated exchange rates."""
    scrape_azure_storage_capacities()
    return Response({"updated_exchange_rates": {}})
