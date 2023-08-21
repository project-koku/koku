#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import typing as t
from copy import deepcopy

from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django_filters import MultipleChoiceFilter
from django_filters.rest_framework import FilterSet
from django_tenants.utils import schema_context
from querystring_parser import parser
from rest_framework.exceptions import ValidationError

from api.currency.currencies import CURRENCIES
from api.currency.currencies import VALID_CURRENCIES
from api.report.constants import URL_ENCODED_SAFE
from api.settings.default_settings import DEFAULT_USER_SETTINGS
from api.user_settings.settings import COST_TYPES
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.user_settings.models import UserSettings

"""Utilities for Settings."""
SETTINGS_PREFIX = "api.settings"
OPENSHIFT_SETTINGS_PREFIX = f"{SETTINGS_PREFIX}.openshift"
OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX = f"{OPENSHIFT_SETTINGS_PREFIX}.tag-management"


class SettingsFilter(FilterSet):
    def generate_cleaned_data(self, name, value):
        """converts data to internal python value, and uses the correct field name"""
        extra_info = self.base_filters.get(name).extra
        if to_field_name := extra_info.get("to_field_name"):
            self.filters[name].field_name = to_field_name

        self.form.cleaned_data[name] = self.filters[name].field.to_python(value)
    def _get_order_by(
        self, order_by_params: t.Union[str, list[str, ...], dict[str, str], None] = None
    ) -> list[str, ...]:
        if order_by_params is None:
            # Default ordering
            return self.Meta.default_ordering

        if isinstance(order_by_params, list):
            # Already a list, just return it.
            translated = []
            for item in order_by_params:
                bare_param = item.lstrip("-")
                if replace := self.Meta.translation.get(bare_param):
                    translated.append(item.replace(bare_param, replace))
                else:
                    translated.append(item)

            return translated

        if isinstance(order_by_params, str):
            # If only one order_by parameter was given, it is a string.
            translated = [order_by_params]
            bare_param = order_by_params.lstrip("-")
            if replace := self.Meta.translation.get(bare_param):
                translated = [order_by_params.replace(bare_param, replace)]

            return translated

        # Support order_by[field]=desc
        if isinstance(order_by_params, dict):
            result = set()
            for field, order in order_by_params.items():
                extra_info = self.base_filters.get(field).extra
                if to_field_name := extra_info.get("to_field_name"):
                    field = to_field_name
                try:
                    # If a field is provided more than once, take the first sorting parameter
                    order = order.pop(0)
                except AttributeError:
                    # Already a str
                    pass

                # Technically we accept "asc" and "desc". Only testing for "desc" to make
                # the API more resilient.
                prefix = "-" if order.lower().startswith("desc") else ""
                result.add(f"{prefix}{field}")

            return list(result)

        # Got something unexpected
        raise ValidationError(f"Invalid order_by parameter: {order_by_params}")

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        order_by = self._get_order_by()

        if self.request:
            query_params = parser.parse(self.request.query_params.urlencode(safe=URL_ENCODED_SAFE))
            filter_params = query_params.get("filter", {})

            # Check valid keys
            invalid_params = set(filter_params).difference(set(self.base_filters))
            if invalid_params:
                msg = "Unsupported parameter or invalid value"
                raise ValidationError({invalid_params.pop(): msg})

            # Multiple choice filter fields need to be a list. If only one filter
            # is provided, it will be a string.

            multiple_choice_fields = [
                field for field, filter in self.base_filters.items() if isinstance(filter, MultipleChoiceFilter)
            ]
            for field in multiple_choice_fields:
                if isinstance(filter_params.get(field), str):
                    filter_params[field] = [filter_params[field]]

            # Use the filter parameters from the request for filtering.
            #
            # The default behavior is to use the URL params directly for filtering.
            # Since our APIs expect filters to be in the filter dict, extract those
            # values and update the cleaned_data, which is used for filtering.
            for name, value in filter_params.items():
                try:
                    self.generate_cleaned_data(name, value)
                except DjangoValidationError as vexc:
                    raise ValidationError(vexc.message % vexc.params)

            order_by = self._get_order_by(query_params.get("order_by"))

        try:
            return super().filter_queryset(queryset).order_by(*order_by)
        except FieldError as fexc:
            raise ValidationError(str(fexc))


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
    return f"https://access.redhat.com/documentation/en-us/cost_management_service/2023/{path}"


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

        if currency_code not in VALID_CURRENCIES:
            raise ValueError(f"{currency_code} is not a supported currency")

        if not account_currency_setting:
            overwrite_default = deepcopy(DEFAULT_USER_SETTINGS)
            overwrite_default["currency"] = currency_code
            UserSettings.objects.create(settings=overwrite_default)
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
            overwrite_default = deepcopy(DEFAULT_USER_SETTINGS)
            overwrite_default["cost_type"] = cost_type_code
            UserSettings.objects.create(settings=overwrite_default)
        else:
            account_current_setting.settings["cost_type"] = cost_type_code
            account_current_setting.save()
