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
"""Test the IAM serializers."""

import random
import uuid

import faker
from django.db.utils import IntegrityError
from rest_framework.exceptions import ValidationError

from api.iam.models import UserPreference
from api.iam.serializers import (AdminCustomerSerializer,
                                 CustomerSerializer,
                                 UserPreferenceSerializer,
                                 UserSerializer,
                                 _currency_symbols,
                                 create_schema_name)
from .iam_test_case import IamTestCase


class CustomerSerializerTest(IamTestCase):
    """Tests for the customer serializer."""

    def test_create_customer(self):
        """Test creating a customer."""
        # create the customers
        customer = self.create_mock_customer_data()
        instance = None
        serializer = CustomerSerializer(data=customer)
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        schema_name = serializer.data.get('schema_name')

        self.assertIsNone(schema_name)
        self.assertFalse('schema_name' in serializer.data)
        self.assertEqual(customer['account_id'], instance.account_id)
        self.assertIsInstance(instance.uuid, uuid.UUID)


class AdminCustomerSerializerTest(IamTestCase):
    """Tests for the admin customer serializer."""

    def test_schema_name_present(self):
        """Test that the serializer contains schema_name."""
        customer = self.create_mock_customer_data()
        serializer = AdminCustomerSerializer(data=customer)
        serializer.is_valid()
        serializer.save()
        expected_schema_name = create_schema_name(serializer.data.get('account_id'))
        schema_name = serializer.data.get('schema_name')
        self.assertIsNotNone(schema_name)
        self.assertEqual(schema_name, expected_schema_name)


class UserSerializerTest(IamTestCase):
    """Tests for the user serializer."""

    def setUp(self):
        """Create test case objects."""
        self.user_data = [self._create_user_data(),
                          self._create_user_data()]

    def test_create_user(self):
        """Test creating a user."""
        # create the users
        for user in self.user_data:
            instance = None
            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertEqual(user['username'], instance.username)

    def test_uuid_field(self):
        """Test that we generate a uuid."""
        # create the user
        instance = None
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        self.assertIsInstance(instance.uuid, uuid.UUID)

    def test_unique_user(self):
        """Test that a user must be unique."""
        # create the user
        serializer_1 = UserSerializer(data=self.user_data[0])
        if serializer_1.is_valid(raise_exception=True):
            serializer_1.save()

        serializer_2 = UserSerializer(data=self.user_data[0])
        with self.assertRaises(ValidationError):
            if serializer_2.is_valid(raise_exception=True):
                serializer_2.save()


class UserPreferenceSerializerTest(IamTestCase):
    """Tests for the user preference serializer."""

    fake = faker.Faker()

    def setUp(self):
        """Create test case objects."""
        from django.conf import settings
        super().setUp()
        self.preference_defaults = [
            {'currency': settings.KOKU_DEFAULT_CURRENCY},
            {'timezone': settings.KOKU_DEFAULT_TIMEZONE},
            {'locale': settings.KOKU_DEFAULT_LOCALE}]

    def test_user_preference_defaults(self):
        """Test that defaults are set for new users."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        query = UserPreference.objects.filter(user__exact=user)
        prefs = [q.preference for q in query]

        for default in self.preference_defaults:
            self.assertIn(default, prefs)

    def test_user_preference_arbitrary(self):
        """Test that we can set and retrieve an arbitrary preference."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        test_pref = {'foo': ['a', [1, 2, 3], {'b': 'c'}]}
        data = {'name': self.fake.word(),
                'description': self.fake.text(),
                'preference': test_pref}
        serializer = UserPreferenceSerializer(data=data, **kwargs)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        query = UserPreference.objects.filter(user__exact=user)
        self.assertEqual(len(query), len(self.preference_defaults) + 1)
        prefs = [q.preference for q in query]
        self.assertIn(test_pref, prefs)

    def test_user_preference_duplicate(self):
        """Test that we fail to create arbitrary preference if it already exits."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        test_pref = {'foo': ['a', [1, 2, 3], {'b': 'c'}]}
        data = {'name': self.fake.word(),
                'description': self.fake.text(),
                'preference': test_pref}
        serializer = UserPreferenceSerializer(data=data, **kwargs)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        with self.assertRaises(IntegrityError):
            serializer = UserPreferenceSerializer(data=data, **kwargs)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_user_preference_locale(self):
        """Test that valid locales are saved."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        data = {'name': 'locale',
                'description': self.fake.text(),
                'preference': {'locale': 'tg_TJ.KOI8-C'}}

        pref = list(UserPreference.objects.filter(user=user, name='locale')).pop()
        self.assertIsNotNone(pref)
        self.assertIsInstance(pref, UserPreference)

        serializer = UserPreferenceSerializer(pref, data=data, **kwargs)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.assertEqual(pref.name, data.get('name'))
        self.assertEqual(pref.description, data.get('description'))
        self.assertEqual(pref.preference, data.get('preference'))

    def test_user_preference_locale_invalid(self):
        """Test that we fail to create invalid preference."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        data = {'name': 'locale',
                'description': self.fake.text(),
                'preference': {'locale': 'squanch.UFC-73'}}

        with self.assertRaises(ValidationError):
            serializer = UserPreferenceSerializer(data=data, **kwargs)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_user_preference_timezone(self):
        """Test that valid timezones are saved."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        data = {'name': 'timezone',
                'description': self.fake.text(),
                'preference': {'timezone': 'Antarctica/Troll'}}

        pref = list(UserPreference.objects.filter(user=user, name='timezone')).pop()
        self.assertIsNotNone(pref)
        self.assertIsInstance(pref, UserPreference)

        serializer = UserPreferenceSerializer(pref, data=data, **kwargs)
        if serializer.is_valid(raise_exception=True):
            pref = serializer.save()

        self.assertEqual(pref.name, data.get('name'))
        self.assertEqual(pref.description, data.get('description'))
        self.assertEqual(pref.preference, data.get('preference'))

    def test_user_preference_timezone_invalid(self):
        """Test that we fail to create invalid preference."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        data = {'name': 'timezone',
                'description': self.fake.text(),
                'preference': {'timezone': 'Glapflap/Parblesnops'}}

        with self.assertRaises(ValidationError):
            serializer = UserPreferenceSerializer(data=data, **kwargs)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_user_preference_currency(self):
        """Test that valid currency codes are saved."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        data = {'name': 'currency',
                'description': self.fake.text(),
                'preference': {'currency': random.choice(_currency_symbols())}}

        pref = list(UserPreference.objects.filter(user=user, name='currency')).pop()
        self.assertIsNotNone(pref)
        self.assertIsInstance(pref, UserPreference)

        serializer = UserPreferenceSerializer(pref, data=data, **kwargs)
        if serializer.is_valid(raise_exception=True):
            pref = serializer.save()

        self.assertEqual(pref.name, data.get('name'))
        self.assertEqual(pref.description, data.get('description'))
        self.assertEqual(pref.preference, data.get('preference'))

    def test_user_preference_currency_invalid(self):
        """Test that we fail to create invalid preference."""
        user = None
        serializer = UserSerializer(data=self.user_data,
                                    context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

        kwargs = {'context': {'user': user}}
        data = {'name': 'currency',
                'description': self.fake.text(),
                'preference': {'currency': 'LOL'}}

        with self.assertRaises(ValidationError):
            serializer = UserPreferenceSerializer(data=data, **kwargs)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
