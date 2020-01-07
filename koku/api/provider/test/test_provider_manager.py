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
import json

from dateutil import parser
from django.http import HttpRequest, QueryDict
from rest_framework.request import Request
from tenant_schemas.utils import tenant_context

from api.iam.models import Customer
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.metrics.models import CostModelMetricsMap
from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource, Sources
from api.provider.provider_manager import ProviderManager, ProviderManagerError
from api.report.test.azure.openshift.helpers import OCPAzureReportDataGenerator
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.report.test.ocp_aws.helpers import OCPAWSReportDataGenerator
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModelMap


class MockResponse:
    """A mock response that can convert response text to json."""

    def __init__(self, status_code, response_text):
        """Initialize the response."""
        self.status_code = status_code
        self.response_text = response_text

    def json(self):
        """Return JSON of response."""
        return json.loads(self.response_text)


class ProviderManagerTest(IamTestCase):
    """Tests for Provider Manager."""

    def setUp(self):
        """Set up the provider manager tests."""
        super().setUp()
        self.customer = Customer.objects.get(
            account_id=self.customer_data['account_id']
        )
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            self.user = serializer.save()

    @staticmethod
    def _create_delete_request(user, headers={}):
        """Delete HTTP request."""
        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        django_request.DELETE = qd
        request = Request(django_request)
        request.user = user
        request.headers = headers
        return request

    @staticmethod
    def _create_put_request(user, headers={}):
        """Delete HTTP request."""
        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        django_request.PUT = qd
        request = Request(django_request)
        request.user = user
        request.headers = headers
        return request

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
        request_context = self._create_request_context(self.create_mock_customer_data(),
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

    def test_remove_aws(self):
        """Remove aws provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='arn:aws:iam::2:role/mg')
        provider_billing = ProviderBillingSource.objects.create(bucket='my_s3_bucket')
        provider = Provider.objects.create(name='awsprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,
                                           billing_source=provider_billing)
        provider_uuid = provider.uuid

        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data,
                                                       new_user_dict, False)
        user_serializer = UserSerializer(data=new_user_dict, context=request_context)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()

        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            manager.remove(self._create_delete_request(other_user))

        provider_query = Provider.objects.all().filter(uuid=provider_uuid)
        auth_count = ProviderAuthentication.objects.count()
        billing_count = ProviderBillingSource.objects.count()
        self.assertFalse(provider_query)
        self.assertEqual(auth_count, 0)
        self.assertEqual(billing_count, 0)

    def test_remove_aws_auth_billing_remain(self):
        """Remove aws provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='arn:aws:iam::2:role/mg')
        provider_authentication2 = ProviderAuthentication.objects.create(
            provider_resource_name='arn:aws:iam::3:role/mg'
        )
        provider_billing = ProviderBillingSource.objects.create(bucket='my_s3_bucket')
        provider = Provider.objects.create(name='awsprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,
                                           billing_source=provider_billing)
        provider2 = Provider.objects.create(name='awsprovidername2',
                                            created_by=self.user,
                                            customer=self.customer,
                                            authentication=provider_authentication2,
                                            billing_source=provider_billing)
        provider_uuid = provider2.uuid

        self.assertNotEqual(provider.uuid, provider2.uuid)
        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data,
                                                       new_user_dict, False)
        user_serializer = UserSerializer(data=new_user_dict, context=request_context)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()

        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            manager.remove(self._create_delete_request(other_user))
        auth_count = ProviderAuthentication.objects.count()
        billing_count = ProviderBillingSource.objects.count()
        provider_query = Provider.objects.all().filter(uuid=provider_uuid)

        self.assertFalse(provider_query)
        self.assertEqual(auth_count, 1)
        self.assertEqual(billing_count, 1)

    def test_remove_ocp(self):
        """Remove ocp provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        provider_uuid = provider.uuid

        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data,
                                                       new_user_dict, False)
        user_serializer = UserSerializer(data=new_user_dict, context=request_context)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()

        with tenant_context(self.tenant):
            ocp_metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
            ocp_source_type = Provider.PROVIDER_OCP
            tiered_rates = [{'unit': 'USD', 'value': 0.22}]
            ocp_data = {
                'name': 'Test Cost Model',
                'description': 'Test',
                'provider_uuids': [],
                'rates': [
                    {
                        'metric': {'name': ocp_metric},
                        'source_type': ocp_source_type,
                        'tiered_rates': tiered_rates
                    }
                ]
            }
            manager = CostModelManager()
            manager.create(**ocp_data)

            manager = ProviderManager(provider_uuid)
            manager.remove(self._create_delete_request(other_user))
            cost_model_query = CostModelMap.objects.all().filter(provider_uuid=provider_uuid)
            self.assertFalse(cost_model_query)
        provider_query = Provider.objects.all().filter(uuid=provider_uuid)
        self.assertFalse(provider_query)

    def test_remove_ocp_added_via_sources(self):
        """Remove ocp provider added via sources."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        provider_uuid = provider.uuid

        sources = Sources.objects.create(source_id=1,
                                         auth_header='testheader',
                                         offset=1,
                                         koku_uuid=provider_uuid)
        sources.save()
        delete_request = self._create_delete_request(self.user, {'Sources-Client': 'True'})
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            manager.remove(delete_request)
        provider_query = Provider.objects.all().filter(uuid=provider_uuid)
        self.assertFalse(provider_query)

    def test_direct_remove_ocp_added_via_sources(self):
        """Remove ocp provider added via sources directly."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        provider_uuid = provider.uuid

        sources = Sources.objects.create(source_id=1,
                                         auth_header='testheader',
                                         offset=1,
                                         koku_uuid=provider_uuid)
        sources.save()
        delete_request = self._create_delete_request(self.user)
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(ProviderManagerError):
                manager.remove(delete_request)

    def test_update_ocp_added_via_sources(self):
        """Raise error on update to ocp provider added via sources."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        provider_uuid = provider.uuid

        sources = Sources.objects.create(source_id=1,
                                         auth_header='testheader',
                                         offset=1,
                                         koku_uuid=provider_uuid)
        sources.save()
        put_request = self._create_put_request(self.user)
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(ProviderManagerError):
                manager.update(put_request)

    def test_update_ocp_not_added_via_sources(self):
        """Return None on update to ocp provider not added via sources."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        provider_uuid = provider.uuid

        put_request = self._create_put_request(self.user)
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            self.assertIsNone(manager.update(put_request))

    def test_provider_statistics(self):
        """Test that the provider statistics method returns report stats."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_OCP,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)

        data_generator = OCPReportDataGenerator(self.tenant, provider)
        data_generator.add_data_to_tenant(**{'provider_uuid': provider.uuid})

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)

        stats = manager.provider_statistics(self.tenant)

        self.assertIn(str(data_generator.dh.this_month_start.date()), stats.keys())
        self.assertIn(str(data_generator.dh.last_month_start.date()), stats.keys())

        for key, value in stats.items():
            key_date_obj = parser.parse(key)
            value_data = value.pop()

            self.assertIsNotNone(value_data.get('assembly_id'))
            self.assertIsNotNone(value_data.get('files_processed'))
            self.assertEqual(value_data.get('billing_period_start'), key_date_obj.date())
            self.assertGreater(parser.parse(value_data.get('last_process_start_date')), key_date_obj)
            self.assertGreater(parser.parse(value_data.get('last_process_complete_date')), key_date_obj)
            self.assertGreater(parser.parse(value_data.get('last_manifest_complete_date')), key_date_obj)
            self.assertGreater(parser.parse(value_data.get('summary_data_creation_datetime')), key_date_obj)
            self.assertGreater(parser.parse(value_data.get('summary_data_updated_datetime')), key_date_obj)
            self.assertGreater(parser.parse(value_data.get('derived_cost_datetime')), key_date_obj)

    def test_provider_statistics_no_report_data(self):
        """Test that the provider statistics method returns no report stats with no report data."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_OCP,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)

        data_generator = OCPReportDataGenerator(self.tenant, provider)
        data_generator.remove_data_from_reporting_common()
        data_generator.remove_data_from_tenant()

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)

        stats = manager.provider_statistics(self.tenant)
        self.assertEqual(stats, {})

    def test_provider_statistics_negative_case(self):
        """Test that the provider statistics method returns None for tenant misalignment."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_AWS,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)

        data_generator = OCPReportDataGenerator(self.tenant, provider)
        data_generator.add_data_to_tenant(**{'provider_uuid': provider.uuid})

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)

        stats = manager.provider_statistics(self.tenant)

        self.assertIn(str(data_generator.dh.this_month_start.date()), stats.keys())
        self.assertIn(str(data_generator.dh.last_month_start.date()), stats.keys())

        for key, value in stats.items():
            key_date_obj = parser.parse(key)
            value_data = value.pop()

            self.assertIsNotNone(value_data.get('assembly_id'))
            self.assertIsNotNone(value_data.get('files_processed'))
            self.assertEqual(value_data.get('billing_period_start'), key_date_obj.date())
            self.assertGreater(parser.parse(value_data.get('last_process_start_date')), key_date_obj)
            self.assertGreater(parser.parse(value_data.get('last_process_complete_date')), key_date_obj)
            self.assertIsNone(value_data.get('summary_data_creation_datetime'))
            self.assertIsNone(value_data.get('summary_data_updated_datetime'))
            self.assertIsNone(value_data.get('derived_cost_datetime'))

    def test_ocp_on_aws_infrastructure_type(self):
        """Test that the provider infrastructure returns AWS when running on AWS."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_AWS,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)

        data_generator = OCPAWSReportDataGenerator(self.tenant, provider, current_month_only=True)
        data_generator.add_data_to_tenant()
        data_generator.add_aws_data_to_tenant()
        data_generator.create_ocp_provider(data_generator.cluster_id, data_generator.cluster_alias)

        provider_uuid = data_generator.provider_uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, Provider.PROVIDER_AWS)

        data_generator.remove_data_from_tenant()

    def test_ocp_on_azure_infrastructure_type(self):
        """Test that the provider infrastructure returns Azure when running on Azure."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1002')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_AZURE,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)

        data_generator = OCPAzureReportDataGenerator(self.tenant, provider, current_month_only=True)
        data_generator.add_data_to_tenant()
        data_generator.create_ocp_provider(data_generator.cluster_id, data_generator.cluster_alias)

        provider_uuid = data_generator.provider_uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, Provider.PROVIDER_AZURE)

        data_generator.remove_data_from_tenant()

    def test_ocp_infrastructure_type(self):
        """Test that the provider infrastructure returns Unknown when running stand alone."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_OCP,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        ocp_aws_data_generator = OCPAWSReportDataGenerator(self.tenant, provider, current_month_only=True)
        data_generator = OCPReportDataGenerator(self.tenant, provider, current_month_only=True)
        data_generator.add_data_to_tenant()
        ocp_aws_data_generator.create_ocp_provider(data_generator.cluster_id, data_generator.cluster_alias)

        provider_uuid = ocp_aws_data_generator.provider_uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, 'Unknown')

        data_generator.remove_data_from_tenant()
        ocp_aws_data_generator.remove_data_from_tenant()

    def test_ocp_infrastructure_type_error(self):
        """Test that the provider infrastructure returns Unknown when running stand alone."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name='cluster_id_1001')
        provider = Provider.objects.create(name='ocpprovidername',
                                           type=Provider.PROVIDER_OCP,
                                           created_by=self.user,
                                           customer=self.customer,
                                           authentication=provider_authentication,)
        data_generator = OCPAWSReportDataGenerator(self.tenant, provider, current_month_only=True)
        data_generator.create_ocp_provider('cool-cluster-id', 'awesome-alias')

        provider_uuid = data_generator.provider_uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, 'Unknown')

        data_generator.remove_data_from_tenant()
