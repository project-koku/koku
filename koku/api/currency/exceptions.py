#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Currency-related exceptions."""
from django.conf import settings
from rest_framework.exceptions import ValidationError


class ExchangeRateNotFound(ValidationError):
    """Raised when no exchange rate exists for a required currency pair."""

    def __init__(self, base_currencies, target_currency, start_date, end_date, missing_months=None):
        missing_pairs = ", ".join(f"{base} -> {target_currency}" for base in base_currencies)
        if missing_months:
            months_str = ", ".join(str(m) for m in sorted(missing_months))
            detail = f"Exchange rate missing for {missing_pairs} for months: {months_str}."
        else:
            detail = f"No exchange rate available for {missing_pairs} for {start_date} to {end_date}."

        if settings.CURRENCY_URL:
            detail += " Ask your administrator to configure static exchange rates."
        else:
            detail += " Ask your administrator to configure static exchange rates or enable dynamic exchange rates."
        super().__init__({"currency": detail})
