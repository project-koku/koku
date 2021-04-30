#
# Copyright 2020 Red Hat, Inc.
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
"""Test the GCP common util."""
import pandas as pd
from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.util.gcp import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill


class TestGCPUtils(MasuTestCase):
    """Tests for GCP utilities."""

    def test_get_bill_ids_from_provider(self):
        """Test that bill IDs are returned for an GCP provider."""
        with schema_context(self.schema):
            expected_bill_ids = GCPCostEntryBill.objects.values_list("id")
            expected_bill_ids = sorted([bill_id[0] for bill_id in expected_bill_ids])
        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted([bill.id for bill in bills])

        self.assertEqual(bill_ids, expected_bill_ids)

        # Try with unknown provider uuid
        bills = utils.get_bills_from_provider(self.unkown_test_provider_uuid, self.schema)
        self.assertEqual(bills, [])

    def test_get_bill_ids_from_provider_with_start_date(self):
        """Test that bill IDs are returned for an GCP provider with start date."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.gcp_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with GCPReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__gte=end_date.date()).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema, start_date=end_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_end_date(self):
        """Test that bill IDs are returned for an GCP provider with end date."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.gcp_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with GCPReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__lte=start_date.date()).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema, end_date=start_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_start_and_end_date(self):
        """Test that bill IDs are returned for an GCP provider with both dates."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.gcp_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with GCPReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = (
                    bills.filter(billing_period_start__gte=start_date.date())
                    .filter(billing_period_start__lte=end_date.date())
                    .all()
                )
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(
            self.gcp_provider_uuid, self.schema, start_date=start_date, end_date=end_date
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_process_gcp_labels(self):
        """Test that labels are formatted properly."""
        label_string = "[{'key': 'key_one', 'value': 'value_one'}, {'key': 'key_two', 'value': 'value_two'}]"

        expected = '{"key_one": "value_one", "key_two": "value_two"}'
        label_result = utils.process_gcp_labels(label_string)

        self.assertEqual(label_result, expected)

    def test_process_gcp_credits(self):
        """Test that credits are formatted properly."""
        credit_string = "[{'first': 'yes', 'second': None, 'third': 'no'}]"

        expected = '{"first": "yes", "second": "None", "third": "no"}'
        credit_result = utils.process_gcp_credits(credit_string)

        self.assertEqual(credit_result, expected)

    def test_post_processor(self):
        """Test that data frame post processing succeeds."""
        data = {"column.one": [1, 2, 3], "column.two": [4, 5, 6], "three": [7, 8, 9]}
        expected_columns = ["column_one", "column_two", "three"]

        df = pd.DataFrame(data)

        result_df = utils.gcp_post_processor(df)
        if isinstance(result_df, tuple):
            result_df, df_tag_keys = result_df
            self.assertIsInstance(df_tag_keys, set)

        result_columns = list(result_df)
        self.assertEqual(sorted(result_columns), sorted(expected_columns))
