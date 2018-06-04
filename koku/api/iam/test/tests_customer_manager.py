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
"""Test the Customer Manager."""

from django.contrib.auth.models import Group

from api.iam.customer_manager import (CustomerManager, CustomerManagerError, CustomerManagerPermissionError)
from api.iam.models import Customer, Tenant, User
from api.iam.serializers import (CustomerSerializer, UserSerializer)
from .iam_test_case import IamTestCase


class CustomerManagerTest(IamTestCase):
    """Tests for Customer Manager."""

    def setUp(self):
        """Set up the Customer Manager tests."""
        super().setUp()
        self.create_service_admin()

    def tearDown(self):
        """Tear down the Customer Manager tests."""
        super().tearDown()

    def test_get_model(self):
        """Can the model object be returned."""
        # Create Customer
        customer = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        manager = CustomerManager(customer_uuid)
        self.assertEqual(manager.get_model(), customer)

    def test_get_name(self):
        """Can the customer name be returned."""
        # Create Customer
        customer = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        manager = CustomerManager(customer_uuid)
        self.assertEqual(manager.get_name(), self.customer_data[0]['name'])

    def test_get_users_for_customer(self):
        """Can current user remove provider."""
        # Create Customer
        customer = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        # Add another user
        group = Group.objects.get(name=customer.name)

        new_user_dict = self.gen_user_data()
        user_serializer = UserSerializer(data=new_user_dict)
        new_user = None
        if user_serializer.is_valid(raise_exception=True):
            new_user = user_serializer.save()
        group.user_set.add(new_user)

        manager = CustomerManager(customer_uuid)
        users = manager.get_users_for_customer()

        self.assertEqual(len(users), 2)

        new_user_found = False
        owner_found = False
        for found_user in users:
            if found_user.username == new_user_dict['username']:
                new_user_found = True
            elif found_user.username == customer.owner.username:
                owner_found = True

        self.assertTrue(new_user_found)
        self.assertTrue(owner_found)

    def test_remove_users(self):
        """Remove users associated with a customer."""
        # Create Customer
        customer = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        # Add another user
        group = Group.objects.get(name=customer.name)

        new_user_dict = self.gen_user_data()
        user_serializer = UserSerializer(data=new_user_dict)
        new_user = None
        if user_serializer.is_valid(raise_exception=True):
            new_user = user_serializer.save()
        group.user_set.add(new_user)

        manager = CustomerManager(customer_uuid)

        # Attempt to remove as customer owner
        with self.assertRaises(CustomerManagerPermissionError):
            manager.remove_users(customer.owner)

        # Attempt to remove as regular user
        with self.assertRaises(CustomerManagerPermissionError):
            manager.remove_users(new_user)

        # Attempt to remove as super user
        superuser = User.objects.filter(is_superuser=True).first()
        manager.remove_users(superuser)

        self.assertFalse(manager.get_users_for_customer())

    def test_invalid_uuid(self):
        """Exception test for invalid uuid."""
        with self.assertRaises(CustomerManagerError):
            uuid = 'invalidid'
            CustomerManager(uuid)

    def test_get_tenant(self):
        """Get the tenant object for a customer."""
        # Create customer.
        customer_name = 'test_customer_tenant'
        customer_json = {'name': customer_name,
                         'owner': self.gen_user_data()}

        customer = None
        serializer = CustomerSerializer(data=customer_json)
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        # Create tenant
        customer_obj = Customer.objects.filter(name=customer_name).get()
        tenant = Tenant(schema_name=customer_obj.schema_name)
        tenant.save()

        # Get manager
        manager = CustomerManager(customer_uuid)
        customer_obj = manager.get_model()
        customer_schema_name = customer_obj.schema_name

        # Verify tenant is returned from manager
        tenant_obj = Tenant.objects.filter(schema_name=customer_schema_name).get()

        self.assertEqual(manager.get_tenant(), tenant_obj)

    def test_get_tenant_not_found(self):
        """Try to get a missing tenant object for a customer."""
        # Create customer.
        customer_name = 'test_customer_tenant'
        customer_json = {'name': customer_name,
                         'owner': self.gen_user_data()}

        customer = None
        serializer = CustomerSerializer(data=customer_json)
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        # Get manager
        manager = CustomerManager(customer_uuid)

        self.assertEqual(manager.get_tenant(), None)

    def test_removing_tenant(self):
        """Remove the tenant object for a customer."""
        # Create customer.
        customer_name = 'test_customer_tenant'
        customer_json = {'name': customer_name,
                         'owner': self.gen_user_data()}

        customer = None
        serializer = CustomerSerializer(data=customer_json)
        if serializer.is_valid(raise_exception=True):
            customer = serializer.save()
        customer_uuid = customer.uuid

        # Create tenant
        customer_obj = Customer.objects.filter(name=customer_name).get()
        tenant = Tenant(schema_name=customer_obj.schema_name)
        tenant.save()

        # Get manager
        manager = CustomerManager(customer_uuid)
        customer_obj = manager.get_model()
        customer_schema_name = customer_obj.schema_name

        # Verify tenant is returned from manager
        tenant_obj = Tenant.objects.filter(schema_name=customer_schema_name).get()

        self.assertEqual(manager.get_tenant(), tenant_obj)

        # Attempt to remove as customer owner
        with self.assertRaises(CustomerManagerPermissionError):
            manager.remove_tenant(customer_obj.owner)

        # Attempt to remove tenant as super user
        superuser = User.objects.filter(is_superuser=True).first()
        manager.remove_tenant(superuser)
