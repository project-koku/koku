#
# Copyright 2019 Red Hat, Inc.
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

"""Test the AzureReportDBCleaner object."""
import datetime

from dateutil import relativedelta
from tenant_schemas.utils import schema_context

from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.processor.azure.azure_report_db_cleaner import (
    AzureReportDBCleaner,
    AzureReportDBCleanerError,
)
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AzureReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AzureReportChargeUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = AzureReportDBAccessor(schema=cls.schema, column_map=cls.column_map)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP['bill'],
            AZURE_REPORT_TABLE_MAP['product'],
            AZURE_REPORT_TABLE_MAP['meter'],
        ]

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        bill_id = self.creator.create_azure_cost_entry_bill(provider_uuid=self.azure_provider_uuid)
        product_id = self.creator.create_azure_cost_entry_product(
            provider_uuid=self.azure_provider_uuid
        )
        meter_id = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        self.creator.create_azure_cost_entry_line_item(bill_id, product_id, meter_id)

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = AzureReportDBCleaner(self.schema)
        with self.assertRaises(AzureReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = AzureReportDBCleaner(self.schema)
        with self.assertRaises(AzureReportDBCleanerError):
            cleaner.purge_expired_report_data(
                expired_date=now, provider_uuid=self.azure_provider_uuid
            )

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('provider_uuid'), first_bill.provider_id)
        self.assertEqual(
            removed_data[0].get('billing_period_start'), str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            earlier_cutoff = cutoff_date.replace(day=15) + relativedelta.relativedelta(months=-1)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(later_cutoff)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('provider_uuid'), first_bill.provider_id)
        self.assertEqual(
            removed_data[0].get('billing_period_start'), str(first_bill.billing_period_start),
        )
        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('provider_uuid'), first_bill.provider_id)
        self.assertEqual(
            removed_data[0].get('billing_period_start'), str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)

        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.azure_provider_uuid)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('provider_uuid'), first_bill.provider_id)
        self.assertEqual(
            removed_data[0].get('billing_period_start'), str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_correct_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider when another provider exists."""
        # add another line item with different provider_uuid
        azure_credentials = {
            'subscription_id': '11111111-f248-4ad7-bfb1-9a4cff600e1d',
            'tenant_id': '11111111-228a-4aee-a215-3a768cdd0105',
            'client_id': '11111111-0f78-42bb-b8e5-90144a025191',
            'client_secret': 'notsosecretcode',
        }
        azure_data_source = {
            'resource_group': 'resourcegroup2',
            'storage_account': 'storageaccount2',
        }
        test_provider_uuid = '11111111-d05f-488c-a6d9-c2a6f3ee02bb'
        azure_auth = ProviderAuthentication.objects.create(credentials=azure_credentials)
        azure_auth.save()
        azure_billing_source = ProviderBillingSource.objects.create(data_source=azure_data_source)
        azure_billing_source.save()
        azure_provider = Provider.objects.create(
            uuid=test_provider_uuid,
            name='Test Provider',
            type=Provider.PROVIDER_AZURE_LOCAL,
            authentication=azure_auth,
            billing_source=azure_billing_source,
            customer=self.customer,
            setup_complete=False,
        )
        azure_provider.save()
        bill_id = self.creator.create_azure_cost_entry_bill(provider_uuid=azure_provider.uuid)
        product_id = self.creator.create_azure_cost_entry_product(provider_uuid=azure_provider.uuid)
        meter_id = self.creator.create_azure_meter(provider_uuid=azure_provider.uuid)
        self.creator.create_azure_cost_entry_line_item(bill_id, product_id, meter_id)

        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()

            self.assertEqual(self.accessor._get_db_obj_query(bill_table_name).all().count(), 2)
            self.assertEqual(self.accessor._get_db_obj_query(line_item_table_name).all().count(), 2)

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.azure_provider_uuid)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('provider_uuid'), first_bill.provider_id)
        self.assertEqual(
            removed_data[0].get('billing_period_start'), str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertEqual(self.accessor._get_db_obj_query(bill_table_name).all().count(), 1)
            self.assertEqual(self.accessor._get_db_obj_query(line_item_table_name).count(), 1)
