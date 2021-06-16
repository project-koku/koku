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
        # Add a bogus provider
        p = Provider(
            uuid=uuid.uuid4(),
            name="eek_provider_3",
            type=Provider.PROVIDER_AWS,
            setup_complete=False,
            active=True,
            customer=c,
        )
        p.save()
        # Create a AWSCostEnrtyBill
        aceb = AWSCostEntryBill(
            billing_resource="6846351687354184651",
            billing_period_start=datetime(2020, 1, 1, tzinfo=UTC),
            billing_period_end=datetime(2020, 2, 1, tzinfo=UTC),
            provider=p,
        )
        expected = "INFO:koku.database:Level 1: delete records from AWSCostEntryBill"
        with schema_context(c.schema_name):
            aceb.save()

        with self.assertLogs("koku.database", level="INFO") as _logger:
            p.delete()
            self.assertIn(expected, _logger.output)

        with schema_context(c.schema_name):
            self.assertEqual(AWSCostEntryBill.objects.filter(pk=aceb.pk).count(), 0)

        self.assertEqual(Provider.objects.filter(pk=p.pk).count(), 0)
