#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Identity and Access Serializers."""
import locale
from base64 import b64decode
from json import loads as json_loads

from django.db import transaction
from rest_framework import serializers

from ..common import error_obj
from ..common import RH_IDENTITY_HEADER
from .models import Customer
from .models import User


def _create_user(username, email, customer):
    """Create a user and associated password reset token."""
    user = User(username=username, email=email, customer=customer)
    user.save()
    return user


def _currency_symbols():
    """Compile a list of valid currency symbols."""
    current = locale.getlocale()
    locales = list(locale.locale_alias.values())
    symbols = set()

    for loc in locales:
        try:
            locale.setlocale(locale.LC_MONETARY, locale.normalize(loc))
            currency = "{int_curr_symbol}".format(**locale.localeconv())
            if currency != "":
                symbols.add(currency.strip())
        except (locale.Error, UnicodeDecodeError):
            continue

    locale.setlocale(locale.LC_MONETARY, current)
    return list(symbols)


def extract_header(request, header):
    """Extract and decode json header.

    Args:
        request(object): The incoming request
        header(str): The header to decode
    Returns:
        JWT(dict): Identity dictionary

    """
    rh_auth_header = request.META[header]
    decoded_rh_auth = b64decode(rh_auth_header)
    json_rh_auth = json_loads(decoded_rh_auth)
    return (rh_auth_header, json_rh_auth)


def create_schema_name(org_id):
    """Create a database schema name."""
    return f"org{org_id}"


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""

    class Meta:
        """Metadata for the serializer."""

        model = User
        fields = ("uuid", "username", "email")

    def get_customer_from_context(self):
        """Get customer from context."""
        customer = self.context.get("customer")
        if customer:
            return customer
        else:
            request = self.context.get("request")
            if request and hasattr(request, "META"):
                _, json_rh_auth = extract_header(request, RH_IDENTITY_HEADER)
                if json_rh_auth and "identity" in json_rh_auth and "org_id" in json_rh_auth["identity"]:
                    org_id = json_rh_auth["identity"]["org_id"]
                if org_id:
                    customer = Customer.objects.get(org_id=org_id)
                else:
                    key = "customer"
                    message = "Customer for requesting user could not be found."
                    raise serializers.ValidationError(error_obj(key, message))
        return customer

    @transaction.atomic
    def create(self, validated_data):
        """Create a user from validated data."""
        user = None
        customer = self.get_customer_from_context()
        user = _create_user(
            username=validated_data.get("username"), email=validated_data.get("email"), customer=customer
        )

        return user


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for the Customer model."""

    class Meta:
        """Metadata for the serializer."""

        model = Customer
        fields = ("uuid", "account_id", "org_id", "date_created")


class AdminCustomerSerializer(CustomerSerializer):
    """Serializer with admin specific fields."""

    class Meta:
        """Metadata for the serializer."""

        model = Customer
        fields = ("uuid", "account_id", "org_id", "date_created", "schema_name")


class NestedUserSerializer(serializers.ModelSerializer):
    """
    User Serializer for nesting inside other serializers.

    This serializer removes uniqueness validation from the username and email
    fields to work around issues documented here:
    https://medium.com/django-rest-framework/dealing-with-unique-constraints-in-nested-serializers-dade33b831d9
    """

    class Meta:
        """Metadata for the serializer."""

        model = User
        fields = ("uuid", "username", "email")
