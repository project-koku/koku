#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency enablement."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.permissions.settings_access import SettingsAccessPermission
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import EnabledCurrency

LOG = logging.getLogger(__name__)


class EnabledCurrencyView(APIView):
    """Enable or disable a single currency for a tenant.

    POST enables the currency; DELETE disables it. No request body required.
    """

    permission_classes = [SettingsAccessPermission]

    def _validate_code(self, code):
        code = code.upper()
        if not is_valid_iso_currency(code):
            return None, Response(
                {"code": [f"Invalid ISO 4217 currency code: {code}"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return code, None

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        code, error = self._validate_code(kwargs["code"])
        if error:
            return error
        EnabledCurrency.objects.get_or_create(currency_code=code)
        LOG.info(log_json(msg="Currency enabled", currency=code))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @method_decorator(never_cache)
    def delete(self, request, *args, **kwargs):
        code, error = self._validate_code(kwargs["code"])
        if error:
            return error
        EnabledCurrency.objects.filter(currency_code=code).delete()
        LOG.info(log_json(msg="Currency disabled", currency=code))
        return Response(status=status.HTTP_204_NO_CONTENT)
