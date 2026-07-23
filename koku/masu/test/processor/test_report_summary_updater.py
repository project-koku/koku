#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportSummaryUpdater object."""
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

from django_tenants.utils import schema_context
from django_tenants.utils import tenant_context

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from cost_models.models import EnabledCurrency
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.processor.azure.azure_report_parquet_summary_updater import AzureReportParquetSummaryUpdater
from masu.processor.report_summary_updater import enable_cloud_bill_currencies
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.test import MasuTestCase
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.models import TenantAPIProvider


class ReportSummaryUpdaterTest(MasuTestCase):
    """Test class for the report summary updater."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.tracing_id = "1234"

    def test_bad_provider_type(self):
        """Test that an unimplemented provider type throws an error."""
        credentials = {"credentials": {"role_arn": "unknown"}}
        self.unknown_auth = ProviderAuthentication.objects.create(credentials=credentials)
        self.unknown_auth.save()
        data_source = {"data_source": {"bucket": "unknown"}}
        self.unknown_billing_source = ProviderBillingSource.objects.create(data_source=data_source)
        self.unknown_billing_source.save()

        with patch("masu.celery.tasks.check_report_updates"):
            self.unknown_provider = Provider.objects.create(
                uuid=self.unkown_test_provider_uuid,
                name="Test Provider",
                type="FOO",
                authentication=self.unknown_auth,
                billing_source=self.unknown_billing_source,
                customer=self.customer,
                setup_complete=False,
                active=True,
            )
        self.unknown_provider.save()

        with self.assertRaises(ReportSummaryUpdaterError):
            _ = ReportSummaryUpdater(self.schema, self.unkown_test_provider_uuid)

    def test_bad_provider(self):
        """Test that an unknown provider uuid throws an error."""
        with self.assertRaises(ReportSummaryUpdaterProviderNotFoundError):
            _ = ReportSummaryUpdater(self.schema, uuid4())

    def test_bad_ocp_provider(self):
        """Test that an OCP provider without cluster-id throws an error."""
        p = self.baker.make("Provider", type="OCP")
        with self.assertRaises(ReportSummaryUpdaterProviderNotFoundError):
            _ = ReportSummaryUpdater(self.schema, p.uuid)

    def test_no_provider_on_create(self):
        """Test that an error is raised when no provider exists."""
        billing_start = self.dh.this_month_start
        no_provider_uuid = uuid4()
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_id": self.ocp_provider_uuid,
        }
        manifest = self.baker.make("CostUsageReportManifest", **manifest_dict)
        manifest_id = manifest.id
        with self.assertRaises(ReportSummaryUpdaterError):
            ReportSummaryUpdater(self.schema, no_provider_uuid, manifest_id)

    def test_aws_parquet_summary_updater(self):
        """Test that the AWSReportParquetSummaryUpdater is returned."""
        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid)

        self.assertIsInstance(updater._updater, AWSReportParquetSummaryUpdater)

    def test_azure_parquet_summary_updater(self):
        """Test that the AzureReportParquetSummaryUpdater is returned."""
        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid)
        self.assertIsInstance(updater._updater, AzureReportParquetSummaryUpdater)

    def _create_aws_summary_with_currency(self, currency_code, provider_name="AWS Currency"):
        """Create an AWS provider and a cost summary row with the given currency."""
        with tenant_context(self.tenant):
            provider = Provider.objects.create(
                name=provider_name,
                type=Provider.PROVIDER_AWS,
                customer=self.customer,
            )
            tenant_provider = TenantAPIProvider.objects.create(
                uuid=provider.uuid, name=provider.name, type=provider.type, provider=provider
            )
            with schema_context(self.schema):
                AWSCostSummaryP.objects.create(
                    id=uuid4(),
                    usage_start="2026-01-15",
                    usage_end="2026-01-15",
                    source_uuid=tenant_provider,
                    currency_code=currency_code,
                )
        return provider

    @patch("masu.processor.report_summary_updater.populate_dynamic_monthly_rates")
    def test_enable_cloud_bill_currencies_enables_missing(self, mock_populate):
        """Cloud bill currencies missing from EnabledCurrency are enabled."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")

        provider = self._create_aws_summary_with_currency("AUD", provider_name="AWS AUD")

        enable_cloud_bill_currencies(self.schema, provider, start_date="2026-01-01", end_date="2026-01-31")

        with tenant_context(self.tenant):
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="AUD").exists())
        mock_populate.assert_called_once_with(code="AUD")

    @patch("masu.processor.report_summary_updater.populate_dynamic_monthly_rates")
    def test_enable_cloud_bill_currencies_skips_invalid_iso(self, mock_populate):
        """Invalid ISO currency codes are skipped without enabling."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")

        provider = self._create_aws_summary_with_currency("FOO", provider_name="AWS Invalid Currency")

        enable_cloud_bill_currencies(self.schema, provider, start_date="2026-01-01", end_date="2026-01-31")

        mock_populate.assert_not_called()
        with tenant_context(self.tenant):
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="FOO").exists())

    @patch("masu.processor.report_summary_updater.populate_dynamic_monthly_rates")
    def test_enable_cloud_bill_currencies_skips_already_enabled(self, mock_populate):
        """Currencies already in EnabledCurrency do not trigger rate population."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="AUD")

        provider = self._create_aws_summary_with_currency("AUD", provider_name="AWS Already Enabled")

        enable_cloud_bill_currencies(self.schema, provider, start_date="2026-01-01", end_date="2026-01-31")

        mock_populate.assert_not_called()

    @patch("masu.processor.report_summary_updater.populate_dynamic_monthly_rates")
    def test_enable_cloud_bill_currencies_skips_when_not_created(self, mock_populate):
        """When get_or_create finds an existing row, rates are not populated again."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")

        provider = self._create_aws_summary_with_currency("AUD", provider_name="AWS Race Currency")
        existing = MagicMock()

        with patch(
            "masu.processor.report_summary_updater.EnabledCurrency.objects.get_or_create",
            return_value=(existing, False),
        ) as mock_get_or_create:
            enable_cloud_bill_currencies(self.schema, provider, start_date="2026-01-01", end_date="2026-01-31")

        mock_get_or_create.assert_called_once_with(currency_code="AUD")
        mock_populate.assert_not_called()

    def test_enable_cloud_bill_currencies_noop_for_non_cloud(self):
        """Non-cloud providers are a no-op."""
        enable_cloud_bill_currencies(self.schema, self.ocp_provider, start_date="2026-01-01", end_date="2026-01-31")

    @patch("masu.processor.report_summary_updater.invalidate_view_cache_for_tenant_and_source_type")
    @patch(
        "masu.processor.report_summary_updater.enable_cloud_bill_currencies",
        side_effect=Exception("enable failed"),
    )
    def test_update_summary_tables_enable_currency_failure_is_swallowed(self, mock_enable, mock_invalidate):
        """Currency enablement failures are logged and do not fail summarization."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.today.date()
        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid)

        with patch.object(updater._updater, "update_summary_tables", return_value=(start_date, end_date)):
            result_start, result_end = updater.update_summary_tables(start_date, end_date, tracing_id=self.tracing_id)

        self.assertEqual(result_start, start_date)
        self.assertEqual(result_end, end_date)
        mock_enable.assert_called_once_with(self.schema, updater._provider, start_date=start_date, end_date=end_date)
        mock_invalidate.assert_called_once_with(self.schema, updater._provider.type)

    @patch("masu.processor.report_summary_updater.OCPCloudParquetReportSummaryUpdater.update_summary_tables")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_openshift_on_cloud_summary_tables(self, mock_select_for_update, mock_update):
        """Test that we run OCP on Cloud summary."""
        start_date = self.dh.this_month_start
        end_date = self.dh.today
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None

        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid, manifest_id=1)
        updater.update_openshift_on_cloud_summary_tables(
            start_date,
            end_date,
            self.ocp_on_azure_ocp_provider.uuid,
            self.azure_provider_uuid,
            Provider.PROVIDER_AZURE,
            tracing_id=1,
        )
        mock_update.assert_called()

        mock_update.reset_mock()

        # Only run for cloud sources that support OCP on Cloud
        updater = ReportSummaryUpdater(self.schema, self.ocp_on_azure_ocp_provider.uuid)
        updater.update_openshift_on_cloud_summary_tables(
            start_date,
            end_date,
            self.ocp_on_azure_ocp_provider.uuid,
            self.azure_provider_uuid,
            Provider.PROVIDER_AZURE,
            tracing_id=1,
        )
        mock_update.assert_not_called()

        mock_update.reset_mock()

        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid, manifest_id=1)
        mock_update.side_effect = Exception
        with self.assertRaises(ReportSummaryUpdaterCloudError):
            updater.update_openshift_on_cloud_summary_tables(
                start_date,
                end_date,
                self.ocp_on_azure_ocp_provider.uuid,
                self.azure_provider_uuid,
                Provider.PROVIDER_AZURE,
                tracing_id=1,
            )
