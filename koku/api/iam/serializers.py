#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Identity and Access Serializers."""
# disabled module-wide due to meta-programming
# pylint: disable=too-few-public-methods
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


def create_schema_name(account):
    """Create a database schema name."""
    return f"acct{account}"


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
                if (
                    json_rh_auth
                    and "identity" in json_rh_auth
                    and "account_number" in json_rh_auth["identity"]  # noqa: W504
                ):
                    account = json_rh_auth["identity"]["account_number"]
                if account:
                    schema_name = create_schema_name(account)
                    customer = Customer.objects.get(schema_name=schema_name)
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
        fields = ("uuid", "account_id", "date_created")


class AdminCustomerSerializer(CustomerSerializer):
    """Serializer with admin specific fields."""

    class Meta:
        """Metadata for the serializer."""

        model = Customer
        fields = ("uuid", "account_id", "date_created", "schema_name")


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
