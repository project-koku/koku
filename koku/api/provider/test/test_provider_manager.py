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
from api.iam.models import Customer
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource
from api.provider.provider_manager import ProviderManager, ProviderManagerError


class ProviderManagerTest(IamTestCase):
    """Tests for Provider Manager."""

    def setUp(self):
        """Set up the provider manager tests."""
        super().setUp()
        self.user_data = self._create_user_data()
        self.current_customer_data = self._create_customer_data()
        self.request_context = self._create_request_context(self.current_customer_data,
                                                            self.user_data)
        self.customer = Customer.objects.get(account_id=self.current_customer_data['account_id'],
                                             org_id=self.current_customer_data['org_id'])
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            self.user = serializer.save()

    def test_get_name(self):
        """Can the provider name be returned."""
        # Create Provider
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertEqual(manager.get_name(), provider_name)

    def test_get_providers_queryset_for_customer(self):
        """Verify all providers returned by a customer."""
        # Verify no providers are returned
        self.assertFalse(ProviderManager.get_providers_queryset_for_customer(self.customer).exists())

        # Create Providers
        provider_1 = Provider.objects.create(name='provider1',
                                             created_by=self.user,
                                             customer=self.customer)
        provider_2 = Provider.objects.create(name='provider2',
                                             created_by=self.user,
                                             customer=self.customer)

        providers = ProviderManager.get_providers_queryset_for_customer(self.customer)
        # Verify providers are returned
        provider_1_found = False
        provider_2_found = False

        for provider in providers:
            if provider.uuid == provider_1.uuid:
                provider_1_found = True
            elif provider.uuid == provider_2.uuid:
                provider_2_found = True

        self.assertTrue(provider_1_found)
        self.assertTrue(provider_2_found)
        self.assertEqual((len(providers)), 2)

    def test_is_removable_by_user(self):
        """Can current user remove provider."""
        # Create Provider
        provider = Provider.objects.create(name='providername',
                                           created_by=self.user,
                                           customer=self.customer)
        provider_uuid = provider.uuid
        user_data = self._create_user_data()
        request_context = self._create_request_context(self._create_customer_data(),
                                                       user_data)
        new_user = None
        serializer = UserSerializer(data=user_data, context=request_context)
        if serializer.is_valid(raise_exception=True):
            new_user = serializer.save()

        manager = ProviderManager(provider_uuid)
        self.assertTrue(manager.is_removable_by_user(self.user))
        self.assertFalse(manager.is_removable_by_user(new_user))

    def test_provider_manager_error(self):
        """Raise ProviderManagerError."""
        with self.assertRaises(ProviderManagerError):
            ProviderManager(uuid='4216c8c7-8809-4381-9a24-bd965140efe2')

        with self.assertRaises(ProviderManagerError):
            ProviderManager(uuid='abc')

    def test_remove(self):
        """Remove provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='arn:aws:iam::2:role/mg')
        provider_billing = ProviderBillingSource.objects.create(bucket='my_s3_bucket')
        provider = Provider.objects.create(name='providername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,
                                           billing_source=provider_billing)
        provider_uuid = provider.uuid

        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.current_customer_data,
                                                       new_user_dict, False)
        user_serializer = UserSerializer(data=new_user_dict, context=request_context)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()

        manager = ProviderManager(provider_uuid)
        manager.remove(other_user)
        provider_query = Provider.objects.all().filter(uuid=provider_uuid)
        self.assertFalse(provider_query)
