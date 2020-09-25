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
import uuid

from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.test import MasuTestCase
from reporting.provider.ocp.models import PRESTO_LINE_ITEM_TABLE_MAP


class OCPReportProcessorParquetTest(MasuTestCase):
    """Test cases for the OCPReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.account = 10001
        self.s3_path = "/s3/path"
        self.provider_uuid = str(uuid.uuid4())
        self.local_parquet = "/local/path"
        self.report_type = "pod_usage"
        self.processor = OCPReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.provider_uuid, self.local_parquet, self.report_type
        )

    def test_ocp_table_name(self):
        """Test the OCP table name generation."""
        self.assertEqual(self.processor._table_name, PRESTO_LINE_ITEM_TABLE_MAP[self.report_type])
