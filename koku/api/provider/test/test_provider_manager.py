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
from unittest.mock import patch

from dateutil import parser
from django.http import HttpRequest
from django.http import QueryDict
from rest_framework.request import Request
from tenant_schemas.utils import tenant_context

from api.iam.models import Customer
from api.iam.models import User
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.provider.models import ProviderInfrastructureMap
from api.provider.models import Sources
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from api.utils import DateHelper
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModelMap
from reporting.models import AWS_MATERIALIZED_VIEWS
from reporting.models import OCP_MATERIALIZED_VIEWS


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
        self.dh = DateHelper()
        self.customer = Customer.objects.get(account_id=self.customer_data["account_id"])
        self.user = User.objects.get(username=self.user_data["username"])

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
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertEqual(manager.get_name(), provider_name)

    def test_get_providers_queryset_for_customer(self):
        """Verify all providers returned by a customer."""
        # Verify no providers are returned
        initial_provider_count = len(ProviderManager.get_providers_queryset_for_customer(self.customer))

        # Create Providers
        with patch("masu.celery.tasks.check_report_updates"):
            provider_1 = Provider.objects.create(name="provider1", created_by=self.user, customer=self.customer)
            provider_2 = Provider.objects.create(name="provider2", created_by=self.user, customer=self.customer)

        providers = ProviderManager.get_providers_queryset_for_customer(self.customer)
        self.assertNotEqual(len(providers), initial_provider_count)

        provider_uuids = [provider.uuid for provider in providers]
        self.assertTrue(provider_1.uuid in provider_uuids)
        self.assertTrue(provider_2.uuid in provider_uuids)
        self.assertEqual(len(providers), initial_provider_count + 2)

    def test_is_removable_by_user(self):
        """Can current user remove provider."""
        # Create Provider
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name="providername", created_by=self.user, customer=self.customer)
        provider_uuid = provider.uuid
        user_data = self._create_user_data()
        request_context = self._create_request_context(self.create_mock_customer_data(), user_data, create_user=False)
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
            ProviderManager(uuid="4216c8c7-8809-4381-9a24-bd965140efe2")

        with self.assertRaises(ProviderManagerError):
            ProviderManager(uuid="abc")

    def test_remove_aws(self):
        """Remove aws provider."""
        # Create Provider
        iniitial_auth_count = ProviderAuthentication.objects.count()
        initial_billing_count = ProviderBillingSource.objects.count()

        provider_authentication = ProviderAuthentication.objects.create(
            provider_resource_name="arn:aws:iam::2:role/mg"
        )
        provider_billing = ProviderBillingSource.objects.create(bucket="my_s3_bucket")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="awsprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                billing_source=provider_billing,
            )
        provider_uuid = provider.uuid

        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data, new_user_dict, False, create_user=False)
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
        self.assertEqual(auth_count, iniitial_auth_count)
        self.assertEqual(billing_count, initial_billing_count)

    def test_remove_all_ocp_providers(self):
        """Remove all OCP providers."""
        provider_query = Provider.objects.all().filter(type="OCP")

        customer = None
        for provider in provider_query:
            customer = provider.customer
            with tenant_context(provider.customer):
                manager = ProviderManager(provider.uuid)
                manager.remove(self._create_delete_request(self.user, {"Sources-Client": "False"}))
        for view in OCP_MATERIALIZED_VIEWS:
            with tenant_context(customer):
                self.assertFalse(view.objects.count())

    def test_remove_all_aws_providers(self):
        """Remove all AWS providers."""
        provider_query = Provider.objects.all().filter(type="AWS-local")

        customer = None
        for provider in provider_query:
            customer = provider.customer
            with tenant_context(provider.customer):
                manager = ProviderManager(provider.uuid)
                manager.remove(self._create_delete_request(self.user, {"Sources-Client": "False"}))
        for view in AWS_MATERIALIZED_VIEWS:
            with tenant_context(customer):
                self.assertFalse(view.objects.count())

    def test_remove_aws_auth_billing_remain(self):
        """Remove aws provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(
            provider_resource_name="arn:aws:iam::2:role/mg"
        )
        expected_auth_count = ProviderAuthentication.objects.count()
        provider_authentication2 = ProviderAuthentication.objects.create(
            provider_resource_name="arn:aws:iam::3:role/mg"
        )
        provider_billing = ProviderBillingSource.objects.create(bucket="my_s3_bucket")
        expected_billing_count = ProviderBillingSource.objects.count()
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="awsprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                billing_source=provider_billing,
            )
            provider2 = Provider.objects.create(
                name="awsprovidername2",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication2,
                billing_source=provider_billing,
            )
        provider_uuid = provider2.uuid

        self.assertNotEqual(provider.uuid, provider2.uuid)
        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data, new_user_dict, False, create_user=False)
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
        self.assertEqual(auth_count, expected_auth_count)
        self.assertEqual(billing_count, expected_billing_count)

    def test_remove_ocp(self):
        """Remove ocp provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )
        provider_uuid = provider.uuid

        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data, new_user_dict, False, create_user=False)
        user_serializer = UserSerializer(data=new_user_dict, context=request_context)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()

        with tenant_context(self.tenant):
            ocp_metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
            ocp_source_type = Provider.PROVIDER_OCP
            tiered_rates = [{"unit": "USD", "value": 0.22}]
            ocp_data = {
                "name": "Test Cost Model",
                "description": "Test",
                "provider_uuids": [],
                "rates": [
                    {"metric": {"name": ocp_metric}, "source_type": ocp_source_type, "tiered_rates": tiered_rates}
                ],
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
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )
        provider_uuid = provider.uuid

        sources = Sources.objects.create(source_id=1, auth_header="testheader", offset=1, koku_uuid=provider_uuid)
        sources.save()
        delete_request = self._create_delete_request(self.user, {"Sources-Client": "True"})
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            manager.remove(delete_request, from_sources=True)
        provider_query = Provider.objects.all().filter(uuid=provider_uuid)
        self.assertFalse(provider_query)

    def test_direct_remove_ocp_added_via_sources(self):
        """Remove ocp provider added via sources directly."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )
        provider_uuid = provider.uuid

        sources = Sources.objects.create(source_id=1, auth_header="testheader", offset=1, koku_uuid=provider_uuid)
        sources.save()
        delete_request = self._create_delete_request(self.user)
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(ProviderManagerError):
                manager.remove(delete_request)

    def test_update_ocp_added_via_sources(self):
        """Raise error on update to ocp provider added via sources."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )
        provider_uuid = provider.uuid

        sources = Sources.objects.create(source_id=1, auth_header="testheader", offset=1, koku_uuid=provider_uuid)
        sources.save()
        put_request = self._create_put_request(self.user)
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(ProviderManagerError):
                manager.update(put_request)

    def test_update_ocp_not_added_via_sources(self):
        """Return None on update to ocp provider not added via sources."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )
        provider_uuid = provider.uuid

        put_request = self._create_put_request(self.user)
        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            self.assertIsNone(manager.update(put_request))

    def test_provider_statistics(self):
        """Test that the provider statistics method returns report stats."""
        provider = Provider.objects.first()

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)

        stats = manager.provider_statistics(self.tenant)

        self.assertIn(str(self.dh.this_month_start.date()), stats.keys())
        self.assertIn(str(self.dh.last_month_start.date()), stats.keys())

        for key, value in stats.items():
            key_date_obj = parser.parse(key)
            value_data = value.pop()

            self.assertIsNotNone(value_data.get("assembly_id"))
            self.assertIsNotNone(value_data.get("files_processed"))
            self.assertEqual(value_data.get("billing_period_start"), key_date_obj.date())
            self.assertGreater(parser.parse(value_data.get("last_process_start_date")), key_date_obj)
            self.assertGreater(parser.parse(value_data.get("last_process_complete_date")), key_date_obj)
            self.assertGreater(parser.parse(value_data.get("last_manifest_complete_date")), key_date_obj)
            self.assertGreater(parser.parse(value_data.get("summary_data_creation_datetime")), key_date_obj)
            self.assertGreater(parser.parse(value_data.get("summary_data_updated_datetime")), key_date_obj)

    def test_provider_statistics_no_report_data(self):
        """Test that the provider statistics method returns no report stats with no report data."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                type=Provider.PROVIDER_OCP,
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)

        stats = manager.provider_statistics(self.tenant)
        self.assertEqual(stats, {})

    def test_ocp_on_aws_infrastructure_type(self):
        """Test that the provider infrastructure returns AWS when running on AWS."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        aws_provider = Provider.objects.filter(type="AWS-local").first()
        infrastructure = ProviderInfrastructureMap.objects.create(
            infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=aws_provider
        )
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                type=Provider.PROVIDER_OCP,
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                infrastructure=infrastructure,
            )

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, Provider.PROVIDER_AWS)

    def test_ocp_on_azure_infrastructure_type(self):
        """Test that the provider infrastructure returns Azure when running on Azure."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1002")
        azure_provider = Provider.objects.filter(type="Azure-local").first()
        infrastructure = ProviderInfrastructureMap.objects.create(
            infrastructure_type=Provider.PROVIDER_AZURE, infrastructure_provider=azure_provider
        )
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                type=Provider.PROVIDER_OCP,
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                infrastructure=infrastructure,
            )

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, Provider.PROVIDER_AZURE)

    def test_ocp_infrastructure_type(self):
        """Test that the provider infrastructure returns Unknown when running stand alone."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                type=Provider.PROVIDER_OCP,
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, "Unknown")

    def test_ocp_infrastructure_type_error(self):
        """Test that the provider infrastructure returns Unknown when running stand alone."""
        provider_authentication = ProviderAuthentication.objects.create(provider_resource_name="cluster_id_1001")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="ocpprovidername",
                type=Provider.PROVIDER_OCP,
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
            )

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)
        infrastructure_name = manager.get_infrastructure_name()
        self.assertEqual(infrastructure_name, "Unknown")

    @patch("api.provider.provider_manager.ProviderManager.is_removable_by_user", return_value=False)
    def test_remove_not_removeable(self, _):
        """Test error raised if user without capability tries to remove a provider."""
        # Create Provider
        provider_authentication = ProviderAuthentication.objects.create(
            provider_resource_name="arn:aws:iam::2:role/mg"
        )
        provider_billing = ProviderBillingSource.objects.create(bucket="my_s3_bucket")
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="awsprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                billing_source=provider_billing,
            )
        provider_uuid = provider.uuid

        new_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data, new_user_dict, False, create_user=False)
        user_serializer = UserSerializer(data=new_user_dict, context=request_context)
        other_user = None
        if user_serializer.is_valid(raise_exception=True):
            other_user = user_serializer.save()

        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(ProviderManagerError):
                manager.remove(self._create_delete_request(other_user))
