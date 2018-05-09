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

from django.test import TestCase

from api.iam.model import Customer, User
from api.iam.serializers import CustomerSerializer, \
                                UserSerializer

from .iam_test_case import IamTestCase

class CustomerSerializerTest(IamTestCase):
    """Tests for the customer serializer."""

    def setUp(self):
        super().setUp()

        # create users to reference in the 'owner' field
        for idx, user in enumerate(self.user_data):
            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
            self.customer_data[idx]['owner'] = User.objects.get(pk=idx+1)

    def test_create_customer(self):
        '''test creating a customer'''
        # create the customers
        for customer in self.customer_data:
            serializer = CustomerSerializer(data=customer)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

        for idx, customer in enumerate(self.customer_data):
            self.assertEqual(customer['name'],
                             Customer.objects.get(pk=idx+1).name)

    def test_update_customer(self):
        '''test updating a customer'''
        # create the customer
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        # update the customer
        new_data = {'name' : 'other_customer',
                    'owner' : User.objects.get(pk=1)}
        new_serializer = CustomerSerializer(Customer.objects.get(pk=1),
                                            new_data)
        if new_serializer.is_valid(raise_exception=True):
            new_serializer.save()

        # test the update
        self.assertEqual(new_data['name'], Customer.objects.get(pk=1).name)

    def test_uuid_field(self):
        '''test that we generate a uuid'''
        # create the customer
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.assertIsInstance(Customer.objects.get(pk=1).customer_id,
                              uuid.UUID)


class UserSerializerTest(IamTestCase):
    """Tests for the user serializer."""

    def test_create_user(self):
        '''test creating a user'''
        # create the users
        for idx, user in enumerate(self.user_data):
            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

        for idx, user in enumerate(self.user_data):
            self.assertEqual(user['username'],
                             User.objects.get(pk=idx+1).username)

            # FIXME: we shouldn't store the password unencrypted.
            self.assertEqual(user['password'],
                             User.objects.get(pk=idx+1).password)

            self.assertEqual(user['first_name'],
                             User.objects.get(pk=idx+1).first_name)

            self.assertEqual(user['last_name'],
                             User.objects.get(pk=idx+1).last_name)

    def test_update_user(self):
        '''test updating a user'''
        # create the user
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        # update the user
        current_user = User.objects.get(pk=1)
        new_data = {'username': current_user.username,
                    'password' : 's3kr!t'}
        new_serializer = UserSerializer(current_user,
                                        new_data)
        if new_serializer.is_valid(raise_exception=True):
            new_serializer.save()

        # test the update
        self.assertEqual(new_data['password'], User.objects.get(pk=1).password)

    def test_uuid_field(self):
        '''test that we generate a uuid'''
        # create the user
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.assertIsInstance(User.objects.get(pk=1).user_id,
                              uuid.UUID)
