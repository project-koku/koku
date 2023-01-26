#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

from pytz import UTC
from tenant_schemas.utils import schema_context

from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.oci.models import OCICostEntryBill
from reporting.provider.ocp.models import OCPUsageReportPeriod


@patch("masu.celery.tasks.delete_archived_data.delay", Mock())
class TestProviderDeleteSQL(IamTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        action_ts = datetime.now().replace(tzinfo=UTC)
        # Add a bogus customer
        c = Customer(
            date_created=action_ts,
            date_updated=action_ts,
            uuid=uuid.uuid4(),
            account_id="918273",
            schema_name="acct918273",
        )
        c.save()
        # Create a customer tenant
        t = Tenant(schema_name=c.schema_name)
        t.save()
        t.create_schema()
        cls._customer = c

    def test_aws_provider_delete(self):
        """Test AWS provider delete cascade"""
        c = self._customer
        # Add some bogus providers
        paws = Provider(
            uuid=uuid.uuid4(),
            name="eek_aws_provider_3",
            type=Provider.PROVIDER_AWS,
            setup_complete=False,
            active=True,
            customer=c,
        )
        paws.save()
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=UTC)
        period_end = datetime(2020, 2, 1, tzinfo=UTC)
        awsceb = AWSCostEntryBill(
            billing_resource="6846351687354184651",
            billing_period_start=period_start,
            billing_period_end=period_end,
            provider=paws,
        )
        with schema_context(c.schema_name):
            awsceb.save()

        expected = "reporting_awscostentrybill"
        expected2 = "DELETE CASCADE BRANCH TO reporting_common_costusagereportmanifest"
        with self.assertLogs("api.provider.models", level="DEBUG") as _logger:
            paws.delete()
            _log_output = "\n".join(_logger.output)
            self.assertIn(expected, _log_output)
            self.assertIn(expected2, _log_output)

        with schema_context(c.schema_name):
            self.assertEqual(AWSCostEntryBill.objects.filter(pk=awsceb.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=paws.pk).count(), 0)

    def test_azure_provider_delete(self):
        """Test Azure provider delete cascade"""
        c = self._customer
        # Add some bogus providers
        pazure = Provider(
            uuid=uuid.uuid4(),
            name="eek_azure_provider_3",
            type=Provider.PROVIDER_AZURE,
            setup_complete=False,
            active=True,
            customer=c,
        )
        pazure.save()
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=UTC)
        period_end = datetime(2020, 2, 1, tzinfo=UTC)
        azureceb = AzureCostEntryBill(
            billing_period_start=period_start, billing_period_end=period_end, provider=pazure
        )
        with schema_context(c.schema_name):
            azureceb.save()

        expected = "reporting_azurecostentrybill"
        expected2 = "DELETE CASCADE BRANCH TO reporting_azuremeter"
        expected3 = "DELETE CASCADE BRANCH TO reporting_common_costusagereportmanifest"
        with self.assertLogs("api.provider.models", level="DEBUG") as _logger:
            pazure.delete()
            _log_output = "\n".join(_logger.output)
            self.assertIn(expected, _log_output)
            self.assertIn(expected2, _log_output)
            self.assertIn(expected3, _log_output)

        with schema_context(c.schema_name):
            self.assertEqual(AzureCostEntryBill.objects.filter(pk=azureceb.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=pazure.pk).count(), 0)

    def test_gcp_provider_delete(self):
        """Test GCP provider delete cascade"""
        c = self._customer
        # Add some bogus providers
        pgcp = Provider(
            uuid=uuid.uuid4(),
            name="eek_gcp_provider_3",
            type=Provider.PROVIDER_GCP,
            setup_complete=False,
            active=True,
            customer=c,
        )
        pgcp.save()
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=UTC)
        period_end = datetime(2020, 2, 1, tzinfo=UTC)
        gcpceb = GCPCostEntryBill(billing_period_start=period_start, billing_period_end=period_end, provider=pgcp)
        with schema_context(c.schema_name):
            gcpceb.save()

        expected = "reporting_gcpcostentrybill"
        expected2 = "DELETE CASCADE BRANCH TO reporting_common_costusagereportmanifest"
        with self.assertLogs("api.provider.models", level="DEBUG") as _logger:
            pgcp.delete()
            _log_output = "\n".join(_logger.output)
            self.assertIn(expected, _log_output)
            self.assertIn(expected2, _log_output)

        with schema_context(c.schema_name):
            self.assertEqual(GCPCostEntryBill.objects.filter(pk=gcpceb.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=pgcp.pk).count(), 0)

    def test_ocp_provider_delete(self):
        """Test OCP provider delete cascade"""
        c = self._customer
        # Add some bogus providers
        pocp = Provider(
            uuid=uuid.uuid4(),
            name="eek_ocp_provider_3",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=c,
        )
        pocp.save()
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=UTC)
        period_end = datetime(2020, 2, 1, tzinfo=UTC)
        ocpurp = OCPUsageReportPeriod(
            cluster_id="584634154687685", report_period_start=period_start, report_period_end=period_end, provider=pocp
        )
        with schema_context(c.schema_name):
            ocpurp.save()

        expected = "reporting_ocpusagereportperiod"
        expected2 = "DELETE CASCADE BRANCH TO reporting_common_costusagereportmanifest"
        with self.assertLogs("api.provider.models", level="DEBUG") as _logger:
            pocp.delete()
            _log_output = "\n".join(_logger.output)
            self.assertIn(expected, _log_output)
            self.assertIn(expected2, _log_output)

        with schema_context(c.schema_name):
            self.assertEqual(OCPUsageReportPeriod.objects.filter(pk=ocpurp.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=pocp.pk).count(), 0)

    def test_oci_provider_delete(self):
        """Test OCI provider delete cascade"""
        c = self._customer
        # Add some bogus providers
        poci = Provider(
            uuid=uuid.uuid4(),
            name="eek_oci_provider_3",
            type=Provider.PROVIDER_OCI,
            setup_complete=False,
            active=True,
            customer=c,
        )
        poci.save()
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=UTC)
        period_end = datetime(2020, 2, 1, tzinfo=UTC)
        ociceb = OCICostEntryBill(
            billing_resource="546315338435",
            billing_period_start=period_start,
            billing_period_end=period_end,
            provider=poci,
        )
        with schema_context(c.schema_name):
            ociceb.save()

        expected = "reporting_ocicostentrybill"
        expected2 = "DELETE CASCADE BRANCH TO reporting_common_costusagereportmanifest"
        with self.assertLogs("api.provider.models", level="DEBUG") as _logger:
            poci.delete()
            _log_output = "\n".join(_logger.output)
            self.assertIn(expected, _log_output)
            self.assertIn(expected2, _log_output)

        with schema_context(c.schema_name):
            self.assertEqual(OCICostEntryBill.objects.filter(pk=ociceb.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=poci.pk).count(), 0)
