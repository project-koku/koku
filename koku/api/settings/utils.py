#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from tenant_schemas.utils import schema_context

from api.currency.currencies import CURRENCIES
from api.settings.default_settings import DEFAULT_USER_SETTINGS
from api.user_settings.settings import COST_TYPES
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.user_settings.models import UserSettings

"""Utilities for Settings."""
SETTINGS_PREFIX = "api.settings"
OPENSHIFT_SETTINGS_PREFIX = f"{SETTINGS_PREFIX}.openshift"
OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX = f"{OPENSHIFT_SETTINGS_PREFIX}.tag-management"


def create_subform(name, title, fields):
    """
    Create a subfrom for the settings.

    Args:
        (String) name - unique name for subform.
        (String) title - Display title.
        (List) fields - List of field components.

    Returns:
        (Dict) - Subform component.
    """
    subform = {"title": title, "name": name, "fields": fields, "component": "sub-form"}
    return subform


def create_plain_text(name, label, variant):
    """
    Create a plain text field for the settings.

    Args:
        (String) name - unique name for switch.
        (String) label - Display text.
        (String) variant - plain text variant. I have no idea why they call it that way.
                           But, it is actually HTML element that will wrap the text (label).

    Returns:
        [Dict] - plain text component.
    """
    plain_text = {"component": "plain-text", "label": label, "name": name, "variant": variant}
    return plain_text


def create_plain_text_with_doc(name, label, doc_link):
    """
    Create a plain text field with links for the settings.

    Args:
        (String) name - unique name for switch.
        (String) label - Display text.
        (Dict) doc_link - documentation props.

    Returns:
        [Dict] - plain text with links component.
    """
    plain_text = {"component": "plain-text-with-links", "text": label, "linkProps": [doc_link], "name": name}
    return plain_text


def generate_doc_link(path):
    """
    Generate cost management link to a given path.

    Args:
        (String) path - path to the documentation.
    """
    return f"https://access.redhat.com/documentation/en-us/cost_management_service/2021/{path}"


def create_dual_list_select(name, left_options=[], right_options=[], **kwargs):
    """
    Create a dual-list-select for the settings.

    Args:
        (String) name - unique name for switch.
        (List) left_options - List of dictionaries.
        (List) right_options - List of dictionaries.

    Returns:
        [Dict] - Subform component.
    """
    dual_list_select = {"component": "dual-list-select", "name": name}
    dual_list_select.update(**kwargs)
    return dual_list_select


def create_select(name, **kwargs):
    """
    Create a select for the settings.

    Args:
        (String) name - unique name for switch.

    Returns:
        [Dict] - Subform component.
    """
    select = {"component": "select", "name": name}
    select.update(**kwargs)
    return select


"""Common utilities and helpers for general user settings."""


def set_default_user_settings():
    """
    sets the default user settings.
    """
    default_settings = DEFAULT_USER_SETTINGS

    UserSettings.objects.create(settings=default_settings)


"""Common utilities and helpers for Currency."""


def get_selected_currency_or_setup(schema):
    """
    get currency and/or setup initial currency

    Args:
        (schema) - user settings schema.

    Returns:
        (schema) - currency.
    """
    with schema_context(schema):
        if not UserSettings.objects.exists():
            set_currency(schema)
        currency = UserSettings.objects.all().first().settings["currency"]
        return currency


def get_currency_options():
    """
    get currency options

    Returns:
        (dict) - options.
    """
    return [
        dict(
            value=currency.get("code"),
            label=f"{currency.get('code')} ({currency.get('symbol')}) - {currency.get('name')}",
        )
        for currency in CURRENCIES
    ]


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
        supported_currency_codes = [code.get("code") for code in CURRENCIES]

        if currency_code not in supported_currency_codes:
            raise ValueError(currency_code + " is not a supported currency")

        if not account_currency_setting:
            set_default_user_settings()
        else:
            account_currency_setting.settings["currency"] = currency_code
            account_currency_setting.save()


"""Common utilities and helpers for Cost_type."""


def get_selected_cost_type_or_setup(schema):
    """
    get cost_type and/or setup initial currency

    Args:
        (schema) - user_settings schema.

    Returns:
        (schema) - user_settings.
    """
    with schema_context(schema):
        if not UserSettings.objects.exists():
            set_default_user_settings()
        cost_type = UserSettings.objects.all().first().settings["cost_type"]
        return cost_type


def get_cost_type_options():
    """
    get cost type options

    Returns:
        (dict) - options.
    """
    return [
        dict(
            value=cost_type.get("code"),
            label=f"{cost_type.get('name')}",
            description=f"{cost_type.get('description')}",
        )
        for cost_type in COST_TYPES
    ]


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
