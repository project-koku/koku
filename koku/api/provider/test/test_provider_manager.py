#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Provider views."""
import json
from datetime import date
from unittest.mock import Mock
from unittest.mock import patch

from dateutil import parser
from django.db import IntegrityError
from django.http import HttpRequest
from django.http import QueryDict
from django_tenants.utils import tenant_context
from model_bakery import baker
from rest_framework.request import Request

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
from api.provider.provider_manager import ProviderProcessingError
from api.utils import DateHelper
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModelMap
from koku.database import get_model
from reporting.provider.aws.models import UI_SUMMARY_TABLES as AWS_UI_SUMMARY_TABLES
from reporting.provider.ocp.models import UI_SUMMARY_TABLES as OCP_UI_SUMMARY_TABLES
from reporting_common.models import CostUsageReportManifest


class MockResponse:
    """A mock response that can convert response text to json."""

    def __init__(self, status_code, response_text):
        """Initialize the response."""
        self.status_code = status_code
        self.response_text = response_text

    def json(self):
        """Return JSON of response."""
        return json.loads(self.response_text)


@patch("masu.celery.tasks.delete_archived_data.delay", Mock())
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

    def test_get_active_status(self):
        """Can the provider active status be returned."""
        # Create Provider
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertTrue(manager.get_active_status())

    def test_get_paused_status(self):
        """Can the provider paused status be returned."""
        # Create Provider
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertFalse(manager.get_paused_status())

    def test_get_state(self):
        """Test getting provider state without a manifest."""
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name="sample_provider", created_by=self.user, customer=self.customer)
        with patch("api.provider.provider_manager.ProviderManager.get_manifest_state") as mock_get_manifest_state:
            mock_get_manifest_state.return_value = None
            manager = ProviderManager(provider.uuid)
            self.assertIsNone(manager.get_state())

    def test_get_manifest_state(self):
        """Test getting the current state for a manifest."""
        datetime = DateHelper().today
        # Create Provider
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="sample_provider_in-progress", created_by=self.user, customer=self.customer
            )
            baker.make(
                CostUsageReportManifest,
                provider=provider,
                billing_period_start_datetime=DateHelper().this_month_start,
                completed_datetime=datetime,
                state={"download": {"start": str(datetime)}},
            )
            manager = ProviderManager(provider.uuid)
            # Case when manifest is in-progress
            self.assertEqual(manager.get_state().get("download"), {"start": str(datetime), "state": "in-progress"})

        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="sample_provider_complete", created_by=self.user, customer=self.customer
            )
            baker.make(
                CostUsageReportManifest,
                provider=provider,
                billing_period_start_datetime=DateHelper().this_month_start,
                completed_datetime=datetime,
                state={"download": {"end": str(datetime)}},
            )
            manager = ProviderManager(provider.uuid)
            # Case when manifest is complete
            self.assertEqual(manager.get_state().get("download"), {"end": str(datetime), "state": "complete"})

        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="sample_provider_failed", created_by=self.user, customer=self.customer
            )
            baker.make(
                CostUsageReportManifest,
                provider=provider,
                billing_period_start_datetime=DateHelper().this_month_start,
                completed_datetime=datetime,
                state={"download": {"failed": str(datetime)}},
            )
            manager = ProviderManager(provider.uuid)
            # Case when manifest is failed
            self.assertEqual(manager.get_state().get("download"), {"failed": str(datetime), "state": "failed"})

    def test_get_last_polling_time(self):
        """Test getting latest polling from for a provider"""
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name="sample_provider", created_by=self.user, customer=self.customer)
        manager = ProviderManager(provider.uuid)
        self.assertEqual(manager.get_last_polling_time(), None)

        expected_time = self.dh.now
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="sample_provider_polling_time",
                created_by=self.user,
                customer=self.customer,
                polling_timestamp=expected_time,
            )
            manager = ProviderManager(provider.uuid)
        self.assertEqual(manager.get_last_polling_time(provider.uuid), expected_time.strftime("%Y-%m-%d %H:%M:%S"))
        self.assertEqual(manager.get_last_polling_time(), expected_time.strftime("%Y-%m-%d %H:%M:%S"))

    def test_data_flags(self):
        """Test the data status flag."""
        # Get Provider UUID

        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        provider_uuid = provider.uuid
        baker.make(
            CostUsageReportManifest,
            provider=provider,
            billing_period_start_datetime=DateHelper().this_month_start,
            completed_datetime=DateHelper().today,
        )

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertTrue(manager.get_current_month_data_exists())
        self.assertFalse(manager.get_previous_month_data_exists())
        self.assertTrue(manager.get_any_data_exists())

    def test_data_flags_manifest_not_complete(self):
        """Test the data status flags when manifest is not complete."""
        # Get Provider UUID

        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        provider_uuid = provider.uuid
        baker.make(
            CostUsageReportManifest, provider=provider, billing_period_start_datetime=DateHelper().this_month_start
        )

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertFalse(manager.get_current_month_data_exists())
        self.assertFalse(manager.get_previous_month_data_exists())
        self.assertFalse(manager.get_any_data_exists())

    def test_data_flags_manifest_last_month(self):
        """Test the status flags when manifest with only last month data."""
        # Get Provider UUID

        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        provider_uuid = provider.uuid
        baker.make(
            CostUsageReportManifest,
            provider=provider,
            billing_period_start_datetime=DateHelper().last_month_start,
            completed_datetime=DateHelper().last_month_end,
        )

        # Get Provider Manager
        manager = ProviderManager(provider_uuid)
        self.assertFalse(manager.get_current_month_data_exists())
        self.assertTrue(manager.get_previous_month_data_exists())
        self.assertTrue(manager.get_any_data_exists())

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

    @patch("api.provider.models.Provider.delete", side_effect=IntegrityError())
    @patch("api.provider.provider_manager.ProviderManager.is_removable_by_user", return_value=True)
    def test_remove_IntegrityError(self, mock_removable, mock_delete):
        """Remove provider IntegrityError."""
        # Create Provider
        credentials = {"role_arn": "arn:aws:iam::2:role/mg"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        data_source = {"bucket": "my_s3_bucket"}
        provider_billing = ProviderBillingSource.objects.create(data_source=data_source)
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="awsprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                billing_source=provider_billing,
            )
        provider_uuid = provider.uuid

        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(IntegrityError):
                manager.remove(self._create_delete_request("test"))

    @patch("api.provider.models.Provider.delete", side_effect=IntegrityError())
    @patch("api.provider.provider_manager.ProviderManager.is_removable_by_user", return_value=True)
    def test_remove_ProviderProcessingError(self, mock_removable, mock_delete):
        """Remove provider ProviderProcessingError."""
        # Create Provider
        credentials = {"role_arn": "arn:aws:iam::2:role/mg"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        data_source = {"bucket": "my_s3_bucket"}
        provider_billing = ProviderBillingSource.objects.create(data_source=data_source)
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(
                name="awsprovidername",
                created_by=self.user,
                customer=self.customer,
                authentication=provider_authentication,
                billing_source=provider_billing,
            )
        provider_uuid = provider.uuid

        with tenant_context(self.tenant):
            manager = ProviderManager(provider_uuid)
            with self.assertRaises(ProviderProcessingError):
                manager.remove(self._create_delete_request("test"), retry_count=1)

    def test_remove_aws(self):
        """Remove aws provider."""
        # Create Provider
        iniitial_auth_count = ProviderAuthentication.objects.count()
        initial_billing_count = ProviderBillingSource.objects.count()

        credentials = {"role_arn": "arn:aws:iam::2:role/mg"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        data_source = {"bucket": "my_s3_bucket"}
        provider_billing = ProviderBillingSource.objects.create(data_source=data_source)
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

    @patch("api.provider.provider_manager.ProviderManager.get_is_provider_processing")
    def test_remove_still_processing(self, mock_is_processing):
        """Test a provider remove while still processing data"""
        mock_is_processing.return_value = True
        provider = Provider.objects.first()
        with tenant_context(self.tenant):
            with self.assertRaises(ProviderProcessingError):
                # Test that we throw an execption instead of deleting
                manager = ProviderManager(str(provider.uuid))
                manager.remove(self._create_delete_request(self.user), from_sources=True, retry_count=0)
                self.assertTrue(Provider.objects.filter(uuid=str(provider.uuid)).exists())
            # Now test that we DO delete after the given number of retries
            manager = ProviderManager(str(provider.uuid))
            manager.remove(self._create_delete_request(self.user), from_sources=True, retry_count=25)
            self.assertFalse(Provider.objects.filter(uuid=str(provider.uuid)).exists())

    def test_remove_all_ocp_providers(self):
        """Remove all OCP providers."""
        provider_query = Provider.objects.all().filter(type=Provider.PROVIDER_OCP)

        customer = None
        for provider in provider_query:
            customer = provider.customer
            with tenant_context(provider.customer):
                manager = ProviderManager(provider.uuid)
                manager.remove(self._create_delete_request(self.user, {"Sources-Client": "False"}))
        for view in OCP_UI_SUMMARY_TABLES:
            with tenant_context(customer):
                model = get_model(view)
                self.assertFalse(model.objects.count())

    @patch("masu.celery.tasks.delete_archived_data")
    def test_remove_all_aws_providers(self, mock_delete_archived_data):
        """Remove all AWS providers."""
        provider_query = Provider.objects.all().filter(type=Provider.PROVIDER_AWS_LOCAL)

        customer = None
        for provider in provider_query:
            customer = provider.customer
            with tenant_context(provider.customer):
                manager = ProviderManager(provider.uuid)
                manager.remove(self._create_delete_request(self.user, {"Sources-Client": "False"}))
            mock_delete_archived_data.delay.assert_called_with(
                customer.schema_name, Provider.PROVIDER_AWS_LOCAL, provider.uuid
            )
        for view in AWS_UI_SUMMARY_TABLES:
            with tenant_context(customer):
                model = get_model(view)
                self.assertFalse(model.objects.count())

    def test_remove_aws_auth_billing_remain(self):
        """Remove aws provider."""
        # Create Provider
        credentials = {"role_arn": "arn:aws:iam::2:role/mg"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)

        expected_auth_count = ProviderAuthentication.objects.count()
        credentials = {"role_arn": "arn:aws:iam::3:role/mg"}
        provider_authentication2 = ProviderAuthentication.objects.create(credentials=credentials)

        data_source = {"bucket": "my_s3_bucket"}
        provider_billing = ProviderBillingSource.objects.create(data_source=data_source)
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
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        provider = Provider.objects.filter(data_updated_timestamp__isnull=False).first()

        self.assertIsNotNone(provider)

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)
        stats = manager.provider_statistics(self.tenant)

        self.assertIn(str(self.dh.this_month_start.date()), stats.keys())
        self.assertIn(str(self.dh.last_month_start.date()), stats.keys())

        for key, value in stats.items():
            if key == "data_updated_date":
                value_data = value
                self.assertIsInstance(parser.parse(value_data), date)
                continue
            elif key == "ocp_on_cloud_data_updated_date":
                if value:
                    self.assertIsInstance(parser.parse(value_data), date)
                continue
            key_date_obj = parser.parse(key)
            manifests = value.get("manifests")
            for manifest in manifests:
                self.assertIsNotNone(manifest.get("assembly_id"))
                self.assertIsNotNone(manifest.get("files_processed"))
                self.assertEqual(manifest.get("billing_period_start"), key_date_obj.date())
                self.assertGreater(parser.parse(manifest.get("process_start_date")), key_date_obj)
                self.assertGreater(parser.parse(manifest.get("process_complete_date")), key_date_obj)
                self.assertGreater(parser.parse(manifest.get("manifest_complete_date")), key_date_obj)

    def test_provider_statistics_ocp_on_cloud(self):
        """Test that the provider statistics method returns report stats."""
        provider_uuid = ProviderInfrastructureMap.objects.first().infrastructure_provider_id
        provider = Provider.objects.filter(uuid=provider_uuid).first()

        self.assertIsNotNone(provider)

        provider_uuid = provider.uuid
        manager = ProviderManager(provider_uuid)
        stats = manager.provider_statistics(self.tenant)

        self.assertIn(str(self.dh.this_month_start.date()), stats.keys())
        self.assertIn(str(self.dh.last_month_start.date()), stats.keys())

        for key, value in stats.items():
            if key == "data_updated_date":
                value_data = value
                self.assertIsInstance(parser.parse(value_data), date)
                continue
            elif key == "ocp_on_cloud_data_updated_date":
                self.assertIsInstance(parser.parse(value_data), date)
                continue
            ocp_on_cloud = value.get("ocp_on_cloud")
            for record in ocp_on_cloud:
                self.assertIsNotNone(record.get("ocp_source_uuid"))
                self.assertIsNotNone(record.get("ocp_on_cloud_updated_datetime"))

    def test_provider_statistics_no_report_data(self):
        """Test that the provider statistics method returns no report stats with no report data."""
        # Create Provider
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        self.assertEqual(stats, {"data_updated_date": None, "ocp_on_cloud_data_updated_date": None})

    def test_ocp_on_aws_infrastructure_type(self):
        """Test that the provider infrastructure returns AWS when running on AWS."""
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        with patch("api.provider.provider_manager.Sources.objects"):
            manager = ProviderManager(provider_uuid)
            infrastructure_info = manager.get_infrastructure_info()
            self.assertEqual(infrastructure_info.get("type", ""), Provider.PROVIDER_AWS)
            self.assertEqual(infrastructure_info.get("uuid", ""), aws_provider.uuid)

    def test_ocp_on_azure_infrastructure_type(self):
        """Test that the provider infrastructure returns Azure when running on Azure."""
        credentials = {"cluster_id": "cluster_id_1002"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        azure_provider = Provider.objects.filter(type="Azure-local").first()

        infrastructure = ProviderInfrastructureMap.objects.create(
            infrastructure_type=Provider.PROVIDER_AZURE,
            infrastructure_provider=azure_provider,
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
        with patch("api.provider.provider_manager.Sources.objects"):
            manager = ProviderManager(provider_uuid)
            infrastructure_info = manager.get_infrastructure_info()
            self.assertEqual(infrastructure_info.get("type", ""), Provider.PROVIDER_AZURE)
            self.assertEqual(infrastructure_info.get("uuid", ""), azure_provider.uuid)

    def test_ocp_infrastructure_type(self):
        """Test that the provider infrastructure returns Unknown when running stand alone."""
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        infrastructure_info = manager.get_infrastructure_info()
        self.assertEqual(infrastructure_info, {})

    def test_ocp_infrastructure_type_error(self):
        """Test that the provider infrastructure returns Unknown when running stand alone."""
        credentials = {"cluster_id": "cluster_id_1001"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
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
        infrastructure_info = manager.get_infrastructure_info()
        self.assertEqual(infrastructure_info, {})

    def test_get_additional_context_ocp_with_manifest(self):
        """Test get_additional_context for an OCP provider with manifest data."""
        credentials = {"cluster_id": "cluster_id_ocp_context"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        provider = Provider.objects.create(
            name="ocp_provider_for_context",
            type=Provider.PROVIDER_OCP,
            created_by=self.user,
            customer=self.customer,
            authentication=provider_authentication,
        )
        manifest = baker.make(
            CostUsageReportManifest,
            provider=provider,
            billing_period_start_datetime=DateHelper().this_month_start,
            operator_version="4.7.0",
            operator_airgapped=False,
            operator_certified=True,
        )

        with patch("api.provider.provider_manager.utils.get_latest_operator_version") as mock_latest_version:
            # Scenario 1: Current version is not the latest
            mock_latest_version.return_value = "4.8.0"
            manager = ProviderManager(provider.uuid)
            additional_context = manager.get_additional_context()

            self.assertIsNotNone(manager.manifest, "Manifest should be loaded by ProviderManager")
            self.assertEqual(manager.manifest.id, manifest.id)
            self.assertEqual(additional_context.get("operator_version"), "4.7.0")
            self.assertEqual(additional_context.get("operator_airgapped"), False)
            self.assertEqual(additional_context.get("operator_certified"), True)
            self.assertEqual(additional_context.get("operator_update_available"), True)
            self.assertEqual(additional_context.get("vm_cpu_core_cost_model_support"), True)

            # Scenario 2: Current version is the latest
            mock_latest_version.return_value = "4.7.0"
            manager_updated_ver = ProviderManager(provider.uuid)
            additional_context_updated = manager_updated_ver.get_additional_context()
            self.assertEqual(additional_context_updated.get("operator_update_available"), False)

            # Scenario 3: Provider has existing additional_context
            provider.additional_context = {"existing_key": "existing_value"}
            provider.save()

            mock_latest_version.return_value = "4.8.0"
            manager_with_existing_context = ProviderManager(provider.uuid)
            additional_context_with_existing = manager_with_existing_context.get_additional_context()

            self.assertEqual(additional_context_with_existing.get("existing_key"), "existing_value")
            self.assertEqual(additional_context_with_existing.get("operator_version"), "4.7.0")
            self.assertEqual(additional_context_with_existing.get("operator_update_available"), True)

    def test_get_additional_context_ocp_no_manifest(self):
        """Test get_additional_context for an OCP provider without manifest data."""
        credentials = {"cluster_id": "cluster_id_ocp_no_manifest"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        provider = Provider.objects.create(
            name="ocp_provider_no_manifest",
            type=Provider.PROVIDER_OCP,
            created_by=self.user,
            customer=self.customer,
            authentication=provider_authentication,
            additional_context={"initial_key": "initial_value"},
        )
        # No manifest created for this provider

        manager = ProviderManager(provider.uuid)  # Manifest will be None
        self.assertIsNone(manager.manifest, "Manifest should be None for this provider")

        additional_context = manager.get_additional_context()
        self.assertEqual(additional_context.get("initial_key"), "initial_value")
        self.assertIsNone(additional_context.get("operator_version"))
        self.assertIsNone(additional_context.get("operator_update_available"))

    def test_get_additional_context_non_ocp_provider(self):
        """Test get_additional_context for a non-OCP provider."""
        aws_credentials = {"account_id": "123456789012"}
        aws_provider_authentication = ProviderAuthentication.objects.create(credentials=aws_credentials)
        aws_provider = Provider.objects.create(
            name="aws_provider_for_context",
            type=Provider.PROVIDER_AWS,
            created_by=self.user,
            customer=self.customer,
            authentication=aws_provider_authentication,
            additional_context={"aws_specific": "some_value"},
        )
        baker.make(
            CostUsageReportManifest,
            provider=aws_provider,
            billing_period_start_datetime=DateHelper().this_month_start,
        )
        manager = ProviderManager(aws_provider.uuid)
        additional_context = manager.get_additional_context()
        self.assertEqual(additional_context.get("aws_specific"), "some_value")
        self.assertIsNone(additional_context.get("operator_version"))

    @patch("api.provider.provider_manager.ProviderManager.is_removable_by_user", return_value=False)
    def test_remove_not_removeable(self, _):
        """Test error raised if user without capability tries to remove a provider."""
        # Create Provider
        credentials = {"role_arn": "arn:aws:iam::2:role/mg"}
        provider_authentication = ProviderAuthentication.objects.create(credentials=credentials)
        data_source = {"bucket": "my_s3_bucket"}
        provider_billing = ProviderBillingSource.objects.create(data_source=data_source)
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
