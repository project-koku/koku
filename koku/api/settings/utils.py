#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import typing as t
from copy import deepcopy

from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import ProhibitNullCharactersValidator
from django.db.models import QuerySet
from django_filters import MultipleChoiceFilter
from django_filters.fields import MultipleChoiceField
from django_filters.rest_framework import FilterSet
from django_tenants.utils import schema_context
from querystring_parser import parser
from rest_framework.exceptions import ValidationError

from api.currency.currencies import VALID_CURRENCIES
from api.report.constants import URL_ENCODED_SAFE
from api.settings.settings import COST_TYPES
from api.settings.settings import DEFAULT_USER_SETTINGS
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.user_settings.models import UserSettings

"""Utilities for Settings."""


class NonValidatingMultipleChoiceField(MultipleChoiceField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validators.append(ProhibitNullCharactersValidator())

    def validate(self, value):
        if isinstance(value, str):
            self.run_validators(value)
        else:
            for val in value:
                self.run_validators(val)


class NonValidatedMultipleChoiceFilter(MultipleChoiceFilter):
    field_class = NonValidatingMultipleChoiceField


class SettingsFilter(FilterSet):
    def _get_order_by(
        self, order_by_params: t.Union[str, list[str, ...], dict[str, str], None] = None
    ) -> list[str, ...]:
        if order_by_params is None:
            # Default ordering
            return self.Meta.default_ordering

        if isinstance(order_by_params, list):
            # Already a list, just return it.
            return order_by_params

        if isinstance(order_by_params, str):
            # If only one order_by parameter was given, it is a string.
            return [order_by_params]

        # Support order_by[field]=desc
        if isinstance(order_by_params, dict):
            result = set()
            for field, order in order_by_params.items():
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

    def _get_field_name(self, field: str) -> tuple[str, str]:
        """Get the field name from the filter and return a filtering prefix if present"""
        prefix = "-" if field.startswith("-") else ""
        field = field.lstrip("-")
        translated_field = getattr(self.filters.get(field, {}), "field_name", field)

        return prefix, translated_field

    def _translate_fields(
        self, order_by_params: t.Union[str, list[str, ...], dict[str, str], None]
    ) -> t.Union[str, list[str, ...], dict[str, str]]:
        """Get the correct field names for the given parameters.

        If the filter has a `to_field` attribute, use that for filtering instead
        of the filter attribute name.

        List and str values are from the standard filtering syntax:

            /?order_by=-field&order_by=key

        A dictionary value comes from this query syntax:

            /?order_by[field]=asc
        """
        if order_by_params is None:
            return

        if isinstance(order_by_params, list):
            result = []
            for param in order_by_params:
                prefix, translated_field = self._get_field_name(param)
                result.append(f"{prefix}{translated_field}")

            return result

        if isinstance(order_by_params, str):
            prefix, translated_field = self._get_field_name(order_by_params)
            return f"{prefix}{translated_field}"

        if isinstance(order_by_params, dict):
            result = {}
            for field, filter in order_by_params.items():
                prefix, translated_field = self._get_field_name(field)
                result[translated_field] = filter

            return result

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
                    self.filters[name].field.validate(value)
                    self.form.cleaned_data[name] = self.filters[name].field.to_python(value)
                except DjangoValidationError as vexc:
                    message = vexc.error_list[0].message
                    params = vexc.error_list[0].params
                    raise ValidationError(message % params)

            order_by = self._get_order_by(self._translate_fields(query_params.get("order_by")))

        try:
            return super().filter_queryset(queryset).order_by(*order_by)
        except FieldError as fexc:
            raise ValidationError(str(fexc))


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
        (currency_code) - currency code based on supported currencies(api.settings.settings.currencies)

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
