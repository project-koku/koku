#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Currency settings."""
import logging

from django.test import RequestFactory

from api.provider.models import Provider
from api.settings.utils import SETTINGS_PREFIX
from currency.common import get_currency_options
from currency.common import get_selected_currency_or_setup
from currency.common import set_currency
from koku.cache import invalidate_view_cache_for_tenant_and_source_type


LOG = logging.getLogger(__name__)


class CurrencySettings:
    """Class for generating currency settings."""

    def __init__(self, request):
        """Initialize settings object with incoming request."""
        self.request = request
        self.factory = RequestFactory()
        self.schema = request.user.customer.schema_name

    def handle_settings(self, settings):
        """
		Handle setting results

		Args:
			(String) settings - settings payload.

		Returns:
			(Bool) - True, if a setting had an effect, False otherwise
		"""
        currency = settings.get("api", {}).get("settings", {}).get("currency", None)
        try:
            stored_currency = get_selected_currency_or_setup(self.schema)
        except Exception as exp:
            LOG.warn(f"Failed to retrieve currency for schema {self.schema}. Reason: {exp}")
            return False
        if currency is None or stored_currency == currency:
            return False

        try:
            set_currency(self.schema, currency)
        except Exception as exp:
            LOG.warn(f"Failed to store new currency settings for schema {self.schema}. Reason: {exp}")
            return False
        invalidate_view_cache_for_tenant_and_source_type(self.schema, Provider.PROVIDER_OCP)
        return True

    def build_settings(self):
        """
		Generate currency settings

		Returns:
			(List) - List of setting items
		"""
        settings = {
            "title": "Currency",
            "fields": [
                {
                    "label": "Select the prefered currency to view Cost Information in",
                    "name": "api.settings.openshift.title",
                    "component": "plain-text",
                },
                {
                    "component": "select",
                    "name": f"{SETTINGS_PREFIX}.currency",
                    "label": "Currency",
                    "options": get_currency_options(),
                    "initialValue": get_selected_currency_or_setup(self.schema),
                },
            ],
        }
        return [settings]
