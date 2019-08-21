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

"""Test the AzureReportProcessor object."""
import logging
import copy
import csv
from tenant_schemas.utils import schema_context

from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor

from masu.processor.azure.azure_report_processor import AzureReportProcessor
from masu.external import GZIP_COMPRESSED, UNCOMPRESSED

from masu.config import Config

from masu.test import MasuTestCase


class AzureReportProcessorTest(MasuTestCase):
    """Test Cases for the AzureReportProcessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.test_report = './koku/masu/test/data/azure/costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv'


        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

        with ReportingCommonDBAccessor() as report_common_db:
            cls.column_map = report_common_db.column_map

        _report_tables = copy.deepcopy(AZURE_REPORT_TABLE_MAP)
        #_report_tables.pop('line_item_daily', None)
        #_report_tables.pop('line_item_daily_summary', None)
        #_report_tables.pop('tags_summary', None)
        cls.report_tables = list(_report_tables.values())
        # Grab a single row of test data to work with
        with open(cls.test_report, 'r') as f:
            reader = csv.DictReader(f)
            cls.row = next(reader)

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.azure_provider_id,
        )

        self.accessor = AzureReportDBAccessor(self.schema, self.column_map)


    def test_initializer(self):
        """Test Azure initializer."""
        self.assertIsNotNone(self.processor._schema_name)
        self.assertIsNotNone(self.processor._report_path)
        self.assertIsNotNone(self.processor._report_name)
        self.assertIsNotNone(self.processor._compression)
        self.assertEqual(
            self.processor._datetime_format, Config.AZURE_DATETIME_STR_FORMAT
        )
        self.assertEqual(
            self.processor._batch_size, Config.REPORT_PROCESSING_BATCH_SIZE
        )

    def test_process(self):
        """Test the processing of an uncompressed Azure file."""
        counts = {}

        report_db = self.accessor
        report_schema = report_db.report_schema
        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count

        expected = f'INFO:masu.processor.azure.azure_report_processor File costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv opened for processing'
        logging.disable(
            logging.NOTSET
        )  # We are currently disabling all logging below CRITICAL in masu/__init__.py
        with self.assertLogs(
            'masu.processor.azure.azure_report_processor', level='INFO'
        ) as logger:
            self.processor.process()
            self.assertIn(expected, logger.output)
        import pdb; pdb.set_trace()
        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()

            self.assertTrue(count > counts[table_name])

    def test_remove_temp_cur_files(self):
        """Test verify temporary files are removed."""
        self.processor.remove_temp_cur_files(self.test_report)
