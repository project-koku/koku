#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid
from datetime import datetime

from pytz import UTC
from tenant_schemas.utils import schema_context

from . import database as kdb
from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.ocp.models import OCPUsageReportPeriod


class TestDeleteSQL(IamTestCase):
    def test_delete_query_sql(self):
        """Test that get_delete_sql returns a delete SQL statement"""
        provider = Provider.objects.first()
        provider_query = Provider.objects.filter(uuid=provider.uuid)
        expected = """delete from "api_provider" where "api_provider"."uuid" = %s"""
        del_sql, params = kdb.get_delete_sql(provider_query)

        self.assertTrue(expected in del_sql.lower())
        self.assertTrue(provider.uuid in params)

    def test_execute_delete_sql(self):
        """Test that execute_delete_sql runs the delete SQL"""
        # Add a bogus provider
        p = Provider(
            uuid=uuid.uuid4(), name="eek_provider_1", type=Provider.PROVIDER_OCP, setup_complete=False, active=True
        )
        p.save()
        # Delete it with SQL
        del_count = kdb.execute_delete_sql(Provider.objects.filter(pk=p.pk))

        self.assertEqual(del_count, 1)
        self.assertIsNone(Provider.objects.filter(pk=p.pk).first())

    def test_update_query_sql(self):
        """Test that get_updated_sql returns a update SQL statement"""
        provider = Provider.objects.first()
        provider_query = Provider.objects.filter(uuid=provider.uuid)
        expected = """update "api_provider" set "setup_complete" = %s where "api_provider"."uuid" = %s"""
        udt_sql, params = kdb.get_update_sql(provider_query, setup_complete=True)

        self.assertTrue(expected in udt_sql.lower())
        self.assertTrue(True in params)
        self.assertTrue(provider.uuid in params)

    def test_execute_update_sql(self):
        """Test that execute_update_sql runs the update SQL"""
        # Add a bogus provider
        p = Provider(
            uuid=uuid.uuid4(), name="eek_provider_2", type=Provider.PROVIDER_OCP, setup_complete=False, active=True
        )
        p.save()
        # Update it with SQL
        udt_count = kdb.execute_update_sql(Provider.objects.filter(pk=p.pk), active=False)

        self.assertEqual(udt_count, 1)
        self.assertEqual(Provider.objects.get(pk=p.pk).active, False)

    def test_cascade_delete_with_skip(self):
        """Test that cascade_delete can walk relations abd skip specified relations"""
        action_ts = datetime.now().replace(tzinfo=UTC)
        # Add a bogus customer
        c = Customer(
            date_created=action_ts,
            date_updated=action_ts,
            uuid=uuid.uuid4(),
            account_id="68461385",
            schema_name="acct68461385",
        )
        c.save()
        # Create a customer tenant
        t = Tenant(schema_name=c.schema_name)
        t.save()
        t.create_schema()
        # Add some bogus providers
        pocp = Provider(
            uuid=uuid.uuid4(),
            name="eek_ocp_provider_30",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=c,
        )
        pocp.save()

        expected1 = "INFO:koku.database:Level 1: delete records from OCPUsageReportPeriod"
        expected2 = "INFO:koku.database:SKIPPING RELATION OCPUsageLineItemDailySummary from caller directive"
        expected3 = "INFO:koku.database:SKIPPING RELATION OCPUsageLineItem from caller directive"
        skip_models = [kdb.get_model("OCPUsageLineItemDailySummary"), kdb.get_model("OCPUsageLineItem")]
        query = Provider.objects.filter(pk=pocp.pk)
        with self.assertLogs("koku.database", level="INFO") as _logger:
            with schema_context(c.schema_name):
                kdb.cascade_delete(Provider, query, skip_relations=skip_models)
            self.assertIn(expected1, _logger.output)
            self.assertIn(expected2, _logger.output)
            self.assertIn(expected3, _logger.output)

        with schema_context(c.schema_name):
            self.assertEqual(OCPUsageReportPeriod.objects.filter(pk=pocp.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=pocp.pk).count(), 0)

    def test_cascade_delete(self):
        """Test that cascade_delete can walk relations to delete FK constraint matched records"""
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
        pazure = Provider(
            uuid=uuid.uuid4(),
            name="eek_azure_provider_3",
            type=Provider.PROVIDER_AZURE,
            setup_complete=False,
            active=True,
            customer=c,
        )
        pazure.save()
        pgcp = Provider(
            uuid=uuid.uuid4(),
            name="eek_gcp_provider_3",
            type=Provider.PROVIDER_GCP,
            setup_complete=False,
            active=True,
            customer=c,
        )
        pgcp.save()
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
        awsceb = AWSCostEntryBill(
            billing_resource="6846351687354184651",
            billing_period_start=period_start,
            billing_period_end=period_end,
            provider=paws,
        )
        azureceb = AzureCostEntryBill(
            billing_period_start=period_start, billing_period_end=period_end, provider=pazure
        )
        gcpceb = GCPCostEntryBill(billing_period_start=period_start, billing_period_end=period_end, provider=pgcp)
        ocpurp = OCPUsageReportPeriod(
            cluster_id="584634154687685", report_period_start=period_start, report_period_end=period_end, provider=pocp
        )
        with schema_context(c.schema_name):
            awsceb.save()
            azureceb.save()
            gcpceb.save()
            ocpurp.save()

        expected = "INFO:koku.database:Level 1: delete records from AWSCostEntryBill"
        with self.assertLogs("koku.database", level="INFO") as _logger:
            paws.delete()
            self.assertIn(expected, _logger.output)

        expected = "INFO:koku.database:Level 1: delete records from AzureCostEntryBill"
        with self.assertLogs("koku.database", level="INFO") as _logger:
            pazure.delete()
            self.assertIn(expected, _logger.output)

        expected = "INFO:koku.database:Level 1: delete records from GCPCostEntryBill"
        with self.assertLogs("koku.database", level="INFO") as _logger:
            pgcp.delete()
            self.assertIn(expected, _logger.output)

        expected = "INFO:koku.database:Level 1: delete records from OCPUsageReportPeriod"
        with self.assertLogs("koku.database", level="INFO") as _logger:
            pocp.delete()
            self.assertIn(expected, _logger.output)

        with schema_context(c.schema_name):
            self.assertEqual(AWSCostEntryBill.objects.filter(pk=awsceb.pk).count(), 0)
            self.assertEqual(AzureCostEntryBill.objects.filter(pk=azureceb.pk).count(), 0)
            self.assertEqual(GCPCostEntryBill.objects.filter(pk=gcpceb.pk).count(), 0)
            self.assertEqual(OCPUsageReportPeriod.objects.filter(pk=ocpurp.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk__in=(paws.pk, pazure.pk, pgcp.pk, pocp.pk)).count(), 0)


class TestLoadModels(IamTestCase):
    def test_loader_updates_module_global(self):
        """Test that the loader will add entries to the module-global dict"""
        kdb.DB_MODELS.clear()
        self.assertEqual(kdb.DB_MODELS, {})

        kdb._load_db_models()
        self.assertNotEqual(kdb.DB_MODELS, {})

    def test_db_models_loaded_on_demand(self):
        """Test that the DB_MODELS module-global dict is loaded on-demand"""
        kdb.DB_MODELS.clear()
        self.assertEqual(kdb.DB_MODELS, {})

        tst_model = kdb.get_model("AWSCostEntryBill")
        self.assertTrue(len(kdb.DB_MODELS) > 0)
        self.assertEqual(tst_model, AWSCostEntryBill)

    def test_model_name_lookup_case_insensitive(self):
        """Test case-insensitive model lookup"""
        self.assertEqual(kdb.get_model("AWSCostEntryBill"), AWSCostEntryBill)
        self.assertEqual(kdb.get_model("awscostentrybill"), AWSCostEntryBill)

    def test_table_name_lookup(self):
        """Test model lookup by table name"""
        self.assertEqual(kdb.get_model("api_provider"), Provider)

    def test_qualified_model_name_lookup(self):
        """Test model lookup by qualified model name (<app>.Model)"""
        self.assertEqual(kdb.get_model("api_provider"), kdb.get_model("api.Provider"))

    def test_model_not_found(self):
        """Test model lookup by qualified model name (<app>.Model)"""
        with self.assertRaises(KeyError):
            kdb.get_model("no_app_here.Eek")
