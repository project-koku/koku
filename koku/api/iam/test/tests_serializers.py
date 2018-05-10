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
            instance = None

            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.customer_data[idx]['owner'] = instance

    def test_create_customer(self):
        '''test creating a customer'''
        # create the customers
        for customer in self.customer_data:
            instance = None

            serializer = CustomerSerializer(data=customer)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertEqual(customer['name'], instance.name)

    def test_update_customer(self):
        '''test updating a customer'''
        # create the customer
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        # update the customer
        username = self.user_data[0]['username']
        cust_name = self.customer_data[0]['name']

        current_customer = Customer.objects.get(name__exact=cust_name)
        updated_customer = None

        new_data = {'name' : 'other_customer',
                    'owner' : User.objects.get(username__exact=username)}
        new_serializer = CustomerSerializer(current_customer, new_data)
        if new_serializer.is_valid(raise_exception=True):
            updated_customer = new_serializer.save()

        # test the update
        self.assertEqual(new_data['name'], updated_customer.name)

    def test_uuid_field(self):
        '''test that we generate a uuid'''
        instance = None

        # create the customer
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        self.assertIsInstance(instance.customer_id, uuid.UUID)


class UserSerializerTest(IamTestCase):
    """Tests for the user serializer."""

    def test_create_user(self):
        '''test creating a user'''
        # create the users
        for user in self.user_data:
            user_obj = None

            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                user_obj = serializer.save()

            self.assertEqual(user['password'], user_obj.password)
            self.assertEqual(user['first_name'], user_obj.first_name)
            self.assertEqual(user['last_name'], user_obj.last_name)

    def test_update_user(self):
        '''test updating a user'''
        # create the user
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        # update the user
        username = self.user_data[0]['username']
        current_user = User.objects.get(username__exact=username)
        updated_user = None

        new_data = {'username': username,
                    'password': 'n3w P4sSw0Rd',
                    'first_name': 'Wade',
                    'last_name': 'Wilson'}
        new_serializer = UserSerializer(current_user,
                                        new_data)
        if new_serializer.is_valid(raise_exception=True):
            updated_user = new_serializer.save()

        # test the update
        self.assertEqual(new_data['password'], updated_user.password)
        self.assertEqual(new_data['first_name'], updated_user.first_name)
        self.assertEqual(new_data['last_name'], updated_user.last_name)

    def test_uuid_field(self):
        '''test that we generate a uuid'''
        instance = None

        # create the user
        serializer = UserSerializer(data=self.user_data[0])
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        self.assertIsInstance(instance.user_id, uuid.UUID)
