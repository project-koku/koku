#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django_tenants.utils import schema_context

from api.currency.currencies import VALID_CURRENCIES
from api.user_settings.settings import COST_TYPES
from api.user_settings.settings import DEFAULT_USER_SETTINGS
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.user_settings.models import UserSettings

"""Utilities for Settings."""


def generate_doc_link(path):
    """
    Generate cost management link to a given path.

    Args:
        (String) path - path to the documentation.
    """
    return f"https://access.redhat.com/documentation/en-us/cost_management_service/2023/{path}"


"""Common utilities and helpers for general user settings."""


def set_default_user_settings():
    """
    sets the default user settings.
    """
    default_settings = DEFAULT_USER_SETTINGS

    UserSettings.objects.create(settings=default_settings)


def set_currency(schema, currency_code=KOKU_DEFAULT_CURRENCY):
    """
    set currency

    Args:
        (schema) - user settings schema.
        (currency_code) - currency code based on supported currencies(api.user_settings.settings.currencies)

    Returns:
        (schema) - user settings.
    """
    with schema_context(schema):
        account_currency_setting = UserSettings.objects.all().first()

        if currency_code not in VALID_CURRENCIES:
            raise ValueError(f"{currency_code} is not a supported currency")

        if not account_currency_setting:
            set_default_user_settings()
        else:
            account_currency_setting.settings["currency"] = currency_code
            account_currency_setting.save()


"""Common utilities and helpers for Cost_type."""


def set_cost_type(schema, cost_type_code=KOKU_DEFAULT_COST_TYPE):
    """
    set cost_type

    Args:
        (schema) - user settings schema.
        (cost_type_code) - cost type code based on supported cost_types(api.usersettings.settings.cost_types)

    Returns:
        (schema) - user settings.
    """
    with schema_context(schema):
        account_current_setting = UserSettings.objects.all().first()
        supported_cost_type_codes = [code.get("code") for code in COST_TYPES]

        if cost_type_code not in supported_cost_type_codes:
            raise ValueError(cost_type_code + " is not a supported cost_type")

        if not account_current_setting:
            set_default_user_settings()
            account_current_setting = UserSettings.objects.all().first()
        account_current_setting.settings["cost_type"] = cost_type_code
        account_current_setting.save()
