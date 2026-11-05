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
            months_str = ", ".join(m.strftime("%Y-%m") for m in sorted(missing_months))
            detail = (
                f"Exchange rate missing to convert costs into {target_currency} for {missing_pairs} "
                f"for months: {months_str}."
            )
        else:
            detail = (
                f"No exchange rate available to convert costs into {target_currency} for {missing_pairs} "
                f"for {start_date} to {end_date}."
            )

        detail += (
            " Costs are stored in the source currency; the requested currency is the conversion target."
            f" Ask your administrator to configure static exchange rates for each missing"
            f" source -> {target_currency} pair (the reverse direction is not used)"
        )
        if settings.CURRENCY_URL:
            detail += "."
        else:
            detail += " or enable dynamic exchange rates."
        super().__init__({"currency": detail})
