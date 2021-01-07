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
"""Test the OCPCloudParquetReportSummaryUpdaterTest."""
import datetime
import decimal
from unittest.mock import Mock
from unittest.mock import patch

from django.db.models import Sum

from api.models import Provider
from api.utils import DateHelper
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.test import MasuTestCase


class OCPCloudParquetReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPCloudParquetReportSummaryUpdaterTest class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.today = self.dh.today

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_tags_summary_table"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary_presto"  # noqa: E501
    )
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.update_summary_infrastructure_cost")
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.aws_get_bills_from_provider")
    def test_update_aws_summary_tables(self, mock_utility, mock_ocp, mock_ocp_on_aws, mock_tag_summary, mock_map):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = Mock()
        first = Mock()
        bill_id = 1
        first.return_value.id = bill_id
        fake_bills.first = first
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with ProviderDBAccessor(self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with ProviderDBAccessor(self.ocp_test_provider_uuid) as provider_accessor:
            credentials = provider_accessor.get_credentials()
        cluster_id = credentials.get("cluster_id")
        mock_map.return_value = {self.ocp_test_provider_uuid: (self.aws_provider_uuid, Provider.PROVIDER_AWS)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="acct10001", provider=provider, manifest=None)
        updater.update_aws_summary_tables(
            self.ocp_test_provider_uuid, self.aws_test_provider_uuid, start_date, end_date
        )
        mock_ocp_on_aws.assert_called_with(
            start_date,
            end_date,
            self.ocp_test_provider_uuid,
            self.aws_test_provider_uuid,
            cluster_id,
            bill_id,
            decimal.Decimal(0),
        )

    @patch("masu.database.cost_model_db_accessor.CostModelDBAccessor.cost_model")
    def test_update_azure_summary_tables(self, mock_cost_model):
        """Test that summary tables are updated correctly."""
        markup = {"value": 10, "unit": "percent"}
        mock_cost_model.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=self.azure_provider, manifest=None)

        updater.update_summary_tables(start_date, end_date)

        summary_table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_daily_summary"]
        with AzureReportDBAccessor(self.schema) as azure_accessor:
            query = azure_accessor._get_db_obj_query(summary_table_name).filter(
                cost_entry_bill__billing_period_start=start_date
            )
            markup_cost = query.aggregate(Sum("markup_cost"))["markup_cost__sum"]
            pretax_cost = query.aggregate(Sum("pretax_cost"))["pretax_cost__sum"]

        self.assertAlmostEqual(markup_cost, pretax_cost * decimal.Decimal(markup.get("value") / 100), places=5)

        daily_summary_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        with OCPReportDBAccessor(self.schema) as ocp_accessor:
            query = ocp_accessor._get_db_obj_query(daily_summary_table_name).filter(
                report_period__provider=self.ocp_on_azure_ocp_provider,
                report_period__report_period_start=self.dh.this_month_start,
            )
            infra_cost = query.aggregate(Sum("infrastructure_raw_cost"))["infrastructure_raw_cost__sum"]
            project_infra_cost = query.aggregate(Sum("infrastructure_project_raw_cost"))[
                "infrastructure_project_raw_cost__sum"
            ]

        self.assertIsNotNone(infra_cost)
        self.assertIsNotNone(project_infra_cost)
        self.assertNotEqual(infra_cost, decimal.Decimal(0))
        self.assertNotEqual(project_infra_cost, decimal.Decimal(0))
