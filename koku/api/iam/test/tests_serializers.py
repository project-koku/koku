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

from django.test import TestCase

from api.iam.model import Customer, User
from api.iam.serializers import CustomerSerializer, \
                                UserSerializer

class CustomerSerializerTest(TestCase):
    """Tests for the customer serializer."""
    def setUp(self):
        self.data = {'name' : 'test_customer'}

    def test_create_customer(self):
        '''test creating a customer'''
        serializer = CustomerSerializer(data=self.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.assertEqual(self.data['name'], Customer.objects.get(pk=1).name)

    def test_update_customer(self):
        '''test updating a customer'''
        # create
        serializer = CustomerSerializer(data=self.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        # update
        new_data = {'name' : 'other_customer'}
        new_serializer = CustomerSerializer(Customer.objects.get(pk=1),
                                            new_data)
        if new_serializer.is_valid(raise_exception=True):
            new_serializer.save()

        # test the update
        self.assertEqual(new_data['name'], Customer.objects.get(pk=1).name)


class UserSerializerTest(TestCase):
    """Tests for the user serializer."""

    def setUp(self):
        self.data = {'username': 'testy',
                     'password': '12345',
                     'first_name' : 'Testy',
                     'last_name' : 'McTesterson'}

    def test_create_user(self):
        '''test creating a user'''
        serializer = UserSerializer(data=self.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.assertEqual(self.data['username'], User.objects.get(pk=1).username)
        self.assertEqual(self.data['first_name'], User.objects.get(pk=1).first_name)
        self.assertEqual(self.data['last_name'], User.objects.get(pk=1).last_name)

    def test_update_user(self):
        '''test updating a user'''
        # create
        serializer = UserSerializer(data=self.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        # update
        current_user = User.objects.get(pk=1)
        new_data = {'username': current_user.username,
                    'password' : 's3kr!t'}
        new_serializer = UserSerializer(current_user,
                                        new_data)
        if new_serializer.is_valid(raise_exception=True):
            new_serializer.save()

        # test the update
        self.assertEqual(new_data['password'], User.objects.get(pk=1).password)
