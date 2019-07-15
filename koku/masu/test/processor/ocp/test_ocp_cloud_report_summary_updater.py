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

from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.ocp.ocp_cloud_summary_updater import OCPCloudReportSummaryUpdater

from tests import MasuTestCase


class OCPCloudReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPCloudReportSummaryUpdaterTest class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.date_accessor = DateAccessor()

    @patch(
        'masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary'
    )
    @patch(
        'masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_cost_summary_table'
    )
    @patch('masu.processor.ocp.ocp_cloud_summary_updater.get_cluster_id_from_provider')
    def test_update_summary_tables_with_ocp_provider(
        self, mock_utility, mock_ocp, mock_ocp_on_aws
    ):
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
            schema='acct10001', provider=provider, manifest=None
        )
        updater.update_summary_tables(start_date_str, end_date_str)

        mock_ocp_on_aws.assert_called_with(
            start_date_str, end_date_str, fake_cluster, []
        )
        mock_ocp.assert_called_with(fake_cluster, start_date_str, end_date_str)

    @patch(
        'masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary'
    )
    @patch(
        'masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_cost_summary_table'
    )
    @patch('masu.processor.ocp.ocp_cloud_summary_updater.get_bills_from_provider')
    def test_update_summary_tables_with_aws_provider(
        self, mock_utility, mock_ocp, mock_ocp_on_aws
    ):
        """Test that summary tables are properly run for an OCP provider."""
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
            schema='acct10001', provider=provider, manifest=None
        )
        updater.update_summary_tables(start_date_str, end_date_str)

        mock_ocp_on_aws.assert_called_with(start_date_str, end_date_str, None, bill_ids)
        mock_ocp.assert_not_called()
