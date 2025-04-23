#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from reporting.models import TenantAPIProvider
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.ocp.models import OCPUsageReportPeriod


def create_test_provider(schema, provider):
    with schema_context(schema):
        tenant_provider = TenantAPIProvider(
            uuid=provider.uuid,
            type=provider.type,
            name=provider.name,
            provider=provider,
        )
        tenant_provider.save()


@patch("masu.celery.tasks.delete_archived_data.delay", Mock())
class TestProviderDeleteSQL(IamTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema_name = "acct918273"
        action_ts = datetime.now().replace(tzinfo=settings.UTC)
        # Add a bogus customer
        c = Customer(
            date_created=action_ts,
            date_updated=action_ts,
            uuid=uuid.uuid4(),
            account_id="918273",
            schema_name=cls.schema_name,
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
        create_test_provider(self.schema_name, paws)
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=settings.UTC)
        period_end = datetime(2020, 2, 1, tzinfo=settings.UTC)
        awsceb = AWSCostEntryBill(
            billing_resource="6846351687354184651",
            billing_period_start=period_start,
            billing_period_end=period_end,
            provider_id=paws.uuid,
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
        create_test_provider(self.schema_name, pazure)
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=settings.UTC)
        period_end = datetime(2020, 2, 1, tzinfo=settings.UTC)
        azureceb = AzureCostEntryBill(
            billing_period_start=period_start,
            billing_period_end=period_end,
            provider_id=pazure.uuid,
        )
        with schema_context(c.schema_name):
            azureceb.save()

        expected = "reporting_azurecostentrybill"
        expected3 = "DELETE CASCADE BRANCH TO reporting_common_costusagereportmanifest"
        with self.assertLogs("api.provider.models", level="DEBUG") as _logger:
            pazure.delete()
            _log_output = "\n".join(_logger.output)
            self.assertIn(expected, _log_output)
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
        create_test_provider(self.schema_name, pgcp)
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=settings.UTC)
        period_end = datetime(2020, 2, 1, tzinfo=settings.UTC)
        gcpceb = GCPCostEntryBill(
            billing_period_start=period_start,
            billing_period_end=period_end,
            provider_id=pgcp.uuid,
        )
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
        create_test_provider(self.schema_name, pocp)
        # Create billing period stuff for each provider
        period_start = datetime(2020, 1, 1, tzinfo=settings.UTC)
        period_end = datetime(2020, 2, 1, tzinfo=settings.UTC)
        ocpurp = OCPUsageReportPeriod(
            cluster_id="584634154687685",
            report_period_start=period_start,
            report_period_end=period_end,
            provider_id=pocp.uuid,
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
