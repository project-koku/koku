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

import pytz
from django.conf import settings
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import Customer, User, UserPreference
from ..common import RH_IDENTITY_HEADER


def _create_default_preferences(user):
    """Set preference defaults for this user."""
    defaults = [{'currency': settings.KOKU_DEFAULT_CURRENCY},
                {'timezone': settings.KOKU_DEFAULT_TIMEZONE},
                {'locale': settings.KOKU_DEFAULT_LOCALE}]

    for pref in defaults:
        data = {'preference': pref,
                'user': model_to_dict(user),
                'name': list(pref.keys())[0],
                'description': _('default preference')}
        serializer = UserPreferenceSerializer(data=data, context={'user': user})
        if serializer.is_valid(raise_exception=True):
            serializer.save()


def _create_user(username, email, customer):
    """Create a user and associated password reset token."""
    user = User(username=username,
                email=email,
                customer=customer)
    user.save()
    _create_default_preferences(user=user)
    return user


def _currency_symbols():
    """Compile a list of valid currency symbols."""
    current = locale.getlocale()
    locales = list(locale.locale_alias.values())
    symbols = set()

    for loc in locales:
        try:
            locale.setlocale(locale.LC_MONETARY, locale.normalize(loc))
            currency = '{int_curr_symbol}'.format(**locale.localeconv())
            if currency is not '':
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
    return json_rh_auth


def create_schema_name(account, org):
    """Create a database schema name."""
    return f'acct{account}org{org}'


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""

    class Meta:
        """Metadata for the serializer."""

        model = User
        fields = ('uuid', 'username', 'email')

    @transaction.atomic
    def create(self, validated_data):
        """Create a user from validated data."""
        user = None
        customer = None
        request = self.context.get('request')
        if request and hasattr(request, 'META'):
            json_rh_auth = extract_header(request, RH_IDENTITY_HEADER)
            if (json_rh_auth and 'identity' in json_rh_auth and
                'account_number' in json_rh_auth['identity'] and
                    'org_id' in json_rh_auth['identity']):
                account = json_rh_auth['identity']['account_number']
                org = json_rh_auth['identity']['org_id']
            if account and org:
                schema_name = create_schema_name(account, org)
                customer = Customer.objects.get(schema_name=schema_name)
            else:
                key = 'customer'
                message = 'Customer for requesting user could not be found.'
                raise serializers.ValidationError(error_obj(key, message))

        user = _create_user(
            username=validated_data.get('username'),
            email=validated_data.get('email'),
            customer=customer)

        return user


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for the Customer model."""

    class Meta:
        """Metadata for the serializer."""

        model = Customer
        fields = ('uuid', 'account_id', 'org_id', 'date_created')


class AdminCustomerSerializer(CustomerSerializer):
    """Serializer with admin specific fields."""

    class Meta:
        """Metadata for the serializer."""

        model = Customer
        fields = ('uuid', 'account_id', 'org_id', 'date_created', 'schema_name')


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
        fields = ('uuid', 'username', 'email')


class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for the UserPreference model."""

    user = NestedUserSerializer(label='User', read_only=True)

    class Meta:
        """Metadata for the serializer."""

        model = UserPreference
        fields = ('uuid', 'name', 'description', 'preference', 'user')

    def _generic_validation(self, data, field, iterable):
        """Validate field data in a generic way.

        Args:
            data (dict) Serializer data
            field (str) Preference field name
            iterable (iterable) Iterable containing valid values

        Raises:
            ValidationError

        Returns:
            None

        """
        if data.get('name') is not field:
            return

        pref = data.get('preference', dict).get(field)

        if pref not in iterable:
            raise serializers.ValidationError(f'Invalid {field}: {pref}')

    def _validate_locale(self, data):
        """Check for a valid locale."""
        self._generic_validation(data, 'locale', locale.locale_alias.values())

    def _validate_currency(self, data):
        """Check for a valid currency."""
        self._generic_validation(data, 'currency', _currency_symbols())

    def _validate_timezone(self, data):
        """Check for a valid timezone."""
        self._generic_validation(data, 'timezone', pytz.all_timezones)

    def validate(self, data):
        """Validate the preference."""
        self._validate_locale(data)
        self._validate_currency(data)
        self._validate_timezone(data)
        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create a preference."""
        user_data = model_to_dict(self.context.get('user'))
        user = User.objects.get(username=user_data['username'])
        validated_data['user_id'] = user.id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update a preference."""
        user_data = model_to_dict(self.context.get('user'))
        user = User.objects.get(username=user_data['username'])
        validated_data['user_id'] = user.id
        return super().update(instance, validated_data)
