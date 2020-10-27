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
"""Test the OCPReportParquetProcessor."""
from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.test import MasuTestCase
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import PRESTO_LINE_ITEM_TABLE_MAP


class OCPReportProcessorParquetTest(MasuTestCase):
    """Test cases for the OCPReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.account = 10001
        self.s3_path = "/s3/path"
        self.provider_uuid = self.ocp_provider_uuid
        self.local_parquet = "/local/path"
        self.report_type = "pod_usage"
        self.processor = OCPReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.provider_uuid, self.local_parquet, self.report_type
        )

    def test_ocp_table_name(self):
        """Test the OCP table name generation."""
        self.assertEqual(self.processor._table_name, PRESTO_LINE_ITEM_TABLE_MAP[self.report_type])

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, OCPUsageLineItemDailySummary)

    def test_create_bill(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start + relativedelta(months=1)
        start_date = bill_date
        end_date = DateHelper().this_month_end + relativedelta(months=1)

        self.processor.create_bill(bill_date.date())

        with schema_context(self.schema):
            report_period = OCPUsageReportPeriod.objects.filter(
                cluster_id=self.ocp_cluster_id,
                report_period_start=start_date,
                report_period_end=end_date,
                provider=self.ocp_provider_uuid,
            )
            self.assertIsNotNone(report_period.first())

    def test_create_bill_with_string_arg(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start + relativedelta(months=1)
        start_date = bill_date
        end_date = DateHelper().this_month_end + relativedelta(months=1)

        self.processor.create_bill(str(bill_date.date()))

        with schema_context(self.schema):
            report_period = OCPUsageReportPeriod.objects.filter(
                cluster_id=self.ocp_cluster_id,
                report_period_start=start_date,
                report_period_end=end_date,
                provider=self.ocp_provider_uuid,
            )
            self.assertIsNotNone(report_period.first())
