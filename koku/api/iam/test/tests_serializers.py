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

import uuid

from django.core import mail
from rest_framework.exceptions import ValidationError

from api.iam.email import SUBJECT
from api.iam.models import ResetToken
from api.iam.serializers import CustomerSerializer, UserSerializer
from .iam_test_case import IamTestCase


class CustomerSerializerTest(IamTestCase):
    """Tests for the customer serializer."""

    def test_create_customer(self):
        """Test creating a customer."""
        # create the customers
        for customer in self.customer_data:
            instance = None
            serializer = CustomerSerializer(data=customer)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertEqual(customer['name'], instance.name)
            self.assertTrue(ResetToken.objects.filter(
                user=instance.owner).exists)

    def test_uuid_field(self):
        """Test that a uuid is generated."""
        # create the customer
        instance = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        self.assertIsInstance(instance.uuid, uuid.UUID)


class UserSerializerTest(IamTestCase):
    """Tests for the user serializer."""

    def setUp(self):
        """Create test case objects."""
        self.user_data = [self.gen_user_data(),
                          self.gen_user_data()]

    def test_create_user(self):
        """Test creating a user."""
        # create the users
        for user in self.user_data:
            outbox_count = len(mail.outbox)
            instance = None
            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertEqual(user['username'], instance.username)
            self.assertIsNotNone(instance.password)
            self.assertTrue(ResetToken.objects.filter(user=instance).exists)
            self.assertEqual(len(mail.outbox), outbox_count + 1)
            self.assertEqual(mail.outbox[0].subject, SUBJECT)

    def test_update_user(self):
        """Test updating a user."""
        # create the user
        instance = None
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        # update the user
        new_data = {'username': instance.username,
                    'email': instance.email,
                    'password': 's3kr!t'}
        new_serializer = UserSerializer(instance,
                                        new_data)
        if new_serializer.is_valid(raise_exception=True):
            instance = new_serializer.save()

        # test the update
        self.assertEqual(new_data['password'], instance.password)

    def test_uuid_field(self):
        """Test that we generate a uuid."""
        # create the user
        instance = None
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        self.assertIsInstance(instance.uuid, uuid.UUID)

    def test_invalid_email(self):
        """Test that we only accept valid e-mail addresses."""
        bad_email_user = {'username': 'foo',
                          'password': 's3kr1t',
                          'email': 'this.is.not.an.email.address'}
        serializer = UserSerializer(data=bad_email_user)
        with self.assertRaises(ValidationError):
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_unique_user(self):
        """Test that a user must be unique."""
        # create the user
        serializer_1 = UserSerializer(data=self.user_data[0])
        if serializer_1.is_valid(raise_exception=True):
            serializer_1.save()

        duplicate_email = self.user_data[0]
        duplicate_email['username'] = 'other_user'

        serializer_2 = UserSerializer(data=duplicate_email)
        with self.assertRaises(ValidationError):
            if serializer_2.is_valid(raise_exception=True):
                serializer_2.save()

    def test_non_password_user(self):
        """Test that a user with no password."""
        # create the user
        gen_user = self.gen_user_data()
        del gen_user['password']
        serializer = UserSerializer(data=gen_user)
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()
        self.assertIsNotNone(instance.password)
