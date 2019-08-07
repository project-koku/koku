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

"""Test the OCPCloudReportSummaryUpdaterTest."""
import datetime
from unittest.mock import patch, Mock
from dateutil import relativedelta

from masu.database import AWS_CUR_TABLE_MAP, OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

from masu.external.date_accessor import DateAccessor
from masu.util.ocp.common import get_cluster_id_from_provider

from masu.processor.ocp.ocp_cloud_summary_updater import OCPCloudReportSummaryUpdater

from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class OCPCloudReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPCloudReportSummaryUpdaterTest class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.date_accessor = DateAccessor()

    def setUp(self):
        """Setup tests."""
        super().setUp()
        self.column_map = ReportingCommonDBAccessor().column_map
        # self.manifest_accessor = ReportManifestDBAccessor()

    def _generate_ocp_on_aws_data(self):
        """Test that the OCP on AWS cost summary table is populated."""
        creator = ReportObjectCreator(
            self.schema,
            self.column_map
        )

        bill_ids = []

        today = DateAccessor().today_with_timezone('UTC')
        last_month = today - relativedelta.relativedelta(months=1)
        resource_id = 'i-12345'

        for cost_entry_date in (today, last_month):
            bill = creator.create_cost_entry_bill(provider_id=self.aws_provider.id, bill_date=cost_entry_date)
            bill_ids.append(str(bill.id))
            cost_entry = creator.create_cost_entry(bill, cost_entry_date)
            product = creator.create_cost_entry_product('Compute Instance')
            pricing = creator.create_cost_entry_pricing()
            reservation = creator.create_cost_entry_reservation()
            creator.create_cost_entry_line_item(
                bill,
                cost_entry,
                product,
                pricing,
                reservation,
                resource_id=resource_id
            )

        with AWSReportDBAccessor(self.schema, self.column_map) as aws_accessor:
            aws_accessor.populate_line_item_daily_table(last_month.date(), today.date(), bill_ids)

        cluster_id = self.ocp_provider_resource_name
        provider_id = self.ocp_provider.id

        for cost_entry_date in (today, last_month):
            period = creator.create_ocp_report_period(cost_entry_date, provider_id=provider_id, cluster_id=cluster_id)
            report = creator.create_ocp_report(period, cost_entry_date)
            creator.create_ocp_usage_line_item(
                period,
                report,
                resource_id=resource_id
            )
        cluster_id = get_cluster_id_from_provider(self.ocp_test_provider_uuid)
        with OCPReportDBAccessor(self.schema, self.column_map) as ocp_accessor:
            ocp_accessor.populate_line_item_daily_table(last_month.date(), today.date(), cluster_id)

    def test_get_infra_db_key_for_provider_type(self):
        """Test db_key private method for OCP-on-AWS infrastructure map."""
        with ProviderDBAccessor(self.ocp_test_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        updater = OCPCloudReportSummaryUpdater(
            schema='acct10001',
            provider=provider,
            manifest=None
        )
        self.assertEqual(updater._get_infra_db_key_for_provider_type('AWS'), 'aws_uuid')
        self.assertEqual(updater._get_infra_db_key_for_provider_type('AWS-local'), 'aws_uuid')
        self.assertEqual(updater._get_infra_db_key_for_provider_type('OCP'), 'ocp_uuid')
        self.assertEqual(updater._get_infra_db_key_for_provider_type('WRONG'), None)

    @patch('masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary')
    @patch('masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_cost_summary_table')
    @patch('masu.processor.ocp.ocp_cloud_summary_updater.OCPCloudReportSummaryUpdater._get_ocp_cluster_id_for_provider')
    def test_update_summary_tables_with_ocp_provider(self, mock_utility,
                                                     mock_ocp, mock_ocp_on_aws):
        """Test that summary tables are properly run for an OCP provider."""
        fake_cluster = 'my-ocp-cluster'
        mock_utility.return_value = fake_cluster
        start_date = self.date_accessor.today_with_timezone('UTC')
        end_date = start_date + datetime.timedelta(days=1)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        with ProviderDBAccessor(self.ocp_test_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        updater = OCPCloudReportSummaryUpdater(
            schema='acct10001',
            provider=provider,
            manifest=None
        )
        updater.update_summary_tables(start_date_str, end_date_str)

        mock_ocp_on_aws.assert_called_with(start_date_str, end_date_str,
                                           fake_cluster, [])
        mock_ocp.assert_called_with(fake_cluster, start_date_str, end_date_str)

    @patch('masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary')
    @patch('masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_cost_summary_table')
    @patch('masu.processor.ocp.ocp_cloud_summary_updater.get_bills_from_provider')
    @patch('masu.processor.ocp.ocp_cloud_summary_updater.OCPCloudReportSummaryUpdater._get_ocp_cluster_id_for_provider')
    def test_update_summary_tables_with_aws_provider(self, mock_cluster_id_utility, mock_utility,
                                                     mock_ocp, mock_ocp_on_aws):
        """Test that summary tables are properly run for an OCP provider."""
        fake_cluster_id = 'my-ocp-cluster'
        mock_cluster_id_utility.return_value = fake_cluster_id

        fake_bills = [Mock(), Mock()]
        fake_bills[0].id = 1
        fake_bills[1].id = 2
        bill_ids = [str(bill.id) for bill in fake_bills]
        mock_utility.return_value = fake_bills
        start_date = self.date_accessor.today_with_timezone('UTC')
        end_date = start_date + datetime.timedelta(days=1)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        with ProviderDBAccessor(self.aws_test_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        updater = OCPCloudReportSummaryUpdater(
            schema='acct10001',
            provider=provider,
            manifest=None
        )
        updater.update_summary_tables(start_date_str, end_date_str)
        mock_ocp_on_aws.assert_called_with(start_date_str, end_date_str,
                                           fake_cluster_id, bill_ids)
        mock_ocp.assert_called_with(fake_cluster_id, start_date_str, end_date_str)

    @patch('masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary')
    @patch('masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_cost_summary_table')
    def test_update_summary_tables_no_ocp_on_aws(self, mock_ocp, mock_ocp_on_aws):
        """Test that summary tables do not run when OCP-on-AWS does not exist."""
        test_provider_list = [self.aws_test_provider_uuid, self.ocp_test_provider_uuid]

        for provider_uuid in test_provider_list:
            start_date = self.date_accessor.today_with_timezone('UTC')
            end_date = start_date + datetime.timedelta(days=1)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')

            with ProviderDBAccessor(provider_uuid) as provider_accessor:
                provider = provider_accessor.get_provider()

            updater = OCPCloudReportSummaryUpdater(
                schema='acct10001',
                provider=provider,
                manifest=None
            )

            updater.update_summary_tables(start_date_str, end_date_str)
            mock_ocp.assert_called()
            mock_ocp_on_aws.assert_not_called()

    def test_update_summary_tables(self):
        """Test that summary tables are updated correctly."""
        self._generate_ocp_on_aws_data()

        start_date = self.date_accessor.today_with_timezone('UTC')
        end_date = start_date + datetime.timedelta(days=1)
        start_date = start_date - relativedelta.relativedelta(months=1)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        with ProviderDBAccessor(self.ocp_test_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        updater = OCPCloudReportSummaryUpdater(
            schema='acct10001',
            provider=provider,
            manifest=None
        )

        with AWSReportDBAccessor(self.schema, self.column_map) as aws_accessor:
            summary_table_name = AWS_CUR_TABLE_MAP['ocp_on_aws_daily_summary']
            query = aws_accessor._get_db_obj_query(summary_table_name)
            initial_count = query.count()

        updater.update_summary_tables(start_date_str, end_date_str)

        with AWSReportDBAccessor(self.schema, self.column_map) as aws_accessor:
            query = aws_accessor._get_db_obj_query(summary_table_name)
            self.assertNotEqual(query.count(), initial_count)
