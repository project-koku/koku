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
"""Test the Provider views."""
from django.contrib.auth.models import Group

from api.iam.models import Customer, User
from api.iam.serializers import (CustomerSerializer, UserSerializer)
from api.iam.test.iam_test_case import IamTestCase
from api.provider.manager import ProviderManager, ProviderManagerError
from api.provider.models import Provider


class ProviderManagerTest(IamTestCase):
    """Tests for Provider Manager."""

    def setUp(self):
        """Set up the provider manager tests."""
        super().setUp()

    def tearDown(self):
        """Tear down the provider manager tests."""
        super().tearDown()
        User.objects.all().delete()
        Customer.objects.all().delete()
        Provider.objects.all().delete()

    def test_is_removable_by_user(self):
        """Can current user remove provider."""
        # Create Customer
        customer = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()

        # Create Provider
        provider = Provider.objects.create(created_by=customer.owner, customer=customer)
        provider_uuid = provider.uuid

        # Create another user for negative tests
        # Add another user
        group = Group.objects.get(name=customer.name)

        new_user_dict = self.gen_user_data()
        user_serializer = UserSerializer(data=new_user_dict)
        new_user = None
        if user_serializer.is_valid(raise_exception=True):
            new_user = user_serializer.save()
        group.user_set.add(new_user)

        manager = ProviderManager(provider_uuid)

        self.assertTrue(manager.is_removable_by_user(customer.owner))
        self.assertFalse(manager.is_removable_by_user(new_user))

    def test_provider_manager_error(self):
        """Raise ProviderManagerError."""
        with self.assertRaises(ProviderManagerError):
            ProviderManager(uuid='4216c8c7-8809-4381-9a24-bd965140efe2')

        with self.assertRaises(ProviderManagerError):
            ProviderManager(uuid='abc')

    def test_remove(self):
        """Remove provider."""
        # Create Customer
        customer = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()

        # Create Provider
        provider = Provider.objects.create(created_by=customer.owner, customer=customer)
        provider_uuid = provider.uuid

        # Create another user for negative tests
        # Add another user
        group = Group.objects.get(name=customer.name)

        new_user_dict = self.gen_user_data()
        user_serializer = UserSerializer(data=new_user_dict)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()
        group.user_set.add(other_user)

        manager = ProviderManager(provider_uuid)

        with self.assertRaises(ProviderManagerError):
            self.assertFalse(manager.remove(other_user))

        manager.remove(customer.owner)
        provider_query = Provider.objects.all().filter(uuid=provider_uuid)
        self.assertFalse(provider_query)
