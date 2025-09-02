#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCP common util."""
from dateutil.relativedelta import relativedelta
from django_tenants.utils import schema_context

from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.test import MasuTestCase
from masu.util.gcp import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill


class TestGCPUtils(MasuTestCase):
    """Tests for GCP utilities."""

    def test_get_bill_ids_from_provider(self):
        """Test that bill IDs are returned for an GCP provider."""
        with schema_context(self.schema):
            expected_bill_ids = GCPCostEntryBill.objects.values_list("id")
            expected_bill_ids = sorted(bill_id[0] for bill_id in expected_bill_ids)
        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted(bill.id for bill in bills)

        self.assertEqual(bill_ids, expected_bill_ids)

        # Try with unknown provider uuid
        bills = utils.get_bills_from_provider(self.unkown_test_provider_uuid, self.schema)
        self.assertEqual(bills, [])

    def test_get_bill_ids_from_provider_with_start_date(self):
        """Test that bill IDs are returned for an GCP provider with start date."""
        with GCPReportDBAccessor(schema=self.schema) as accessor:
            end_date = self.dh.this_month_start
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider_uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__gte=end_date).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema, start_date=end_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_end_date(self):
        """Test that bill IDs are returned for an GCP provider with end date."""
        with GCPReportDBAccessor(schema=self.schema) as accessor:
            end_date = self.dh.this_month_start
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider_uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__lte=start_date).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema, end_date=start_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_start_and_end_date(self):
        """Test that bill IDs are returned for an GCP provider with both dates."""
        with GCPReportDBAccessor(schema=self.schema) as accessor:
            end_date = self.dh.this_month_start
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider_uuid)
            with schema_context(self.schema):
                bills = (
                    bills.filter(billing_period_start__gte=start_date).filter(billing_period_start__lte=end_date).all()
                )
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(
            self.gcp_provider_uuid, self.schema, start_date=start_date, end_date=end_date
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)
