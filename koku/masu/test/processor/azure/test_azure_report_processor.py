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
import datetime
import logging
import json
import copy
import csv
import tempfile
import shutil
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external import GZIP_COMPRESSED, UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.processor.azure.azure_report_processor import AzureReportProcessor
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
        _report_tables.pop('line_item_daily_summary', None)
        _report_tables.pop('tags_summary', None)
        cls.report_tables = list(_report_tables.values())
        # Grab a single row of test data to work with
        with open(cls.test_report, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            cls.row = next(reader)

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.assembly_id = '1234'
        self.processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.azure_provider_uuid,
        )

        billing_start = self.date_accessor.today_with_timezone('UTC').replace(
            year=2018, month=6, day=1, hour=0, minute=0, second=0
        )
        self.assembly_id = '1234'
        self.manifest_dict = {
            'assembly_id': self.assembly_id,
            'billing_period_start_datetime': billing_start,
            'num_total_files': 1,
            'provider_uuid': self.azure_provider_uuid,
        }

        self.accessor = AzureReportDBAccessor(self.schema, self.column_map)
        self.report_schema = self.accessor.report_schema
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()

    def test_azure_initializer(self):
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

    def test_azure_process(self):
        """Test the processing of an uncompressed Azure file."""
        counts = {}

        report_db = self.accessor
        report_schema = report_db.report_schema
        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count
        logging.disable(
            logging.NOTSET
        )  # We are currently disabling all logging below CRITICAL in masu/__init__.py
        with self.assertLogs(
            'masu.processor.azure.azure_report_processor', level='INFO'
        ) as logger:
            self.processor.process()
            self.assertIn('INFO:masu.processor.azure.azure_report_processor', logger.output[0])
            self.assertIn('costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv', logger.output[0])

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            self.assertTrue(count > counts[table_name])

    def test_process_azure_small_batches(self):
        """Test the processing of an uncompressed azure file in small batches."""
        with patch.object(Config, 'REPORT_PROCESSING_BATCH_SIZE', 1):
            # Re-init processor so that REPORT_PROCESSING_BATCH_SIZE is 1.
            self.processor = AzureReportProcessor(
                schema_name=self.schema,
                report_path=self.test_report,
                compression=UNCOMPRESSED,
                provider_uuid=self.azure_provider_uuid,
            )

            # Re-run test with new configuration and verify it's still successful.
            self.test_azure_process()

    def notest_process_azure_small_batches(self):
        """Test the processing of an uncompressed azure file in small batches."""
        with patch.object(Config, 'REPORT_PROCESSING_BATCH_SIZE', 1):
            counts = {}

            processor = AzureReportProcessor(
                schema_name=self.schema,
                report_path=self.test_report,
                compression=UNCOMPRESSED,
                provider_uuid=self.azure_provider_uuid,
            )
            report_db = self.accessor
            report_schema = report_db.report_schema
            for table_name in self.report_tables:
                table = getattr(report_schema, table_name)
                with schema_context(self.schema):
                    count = table.objects.count()
                counts[table_name] = count
            logging.disable(
                logging.NOTSET
            )  # We are currently disabling all logging below CRITICAL in masu/__init__.py
            with self.assertLogs(
                'masu.processor.azure.azure_report_processor', level='INFO'
            ) as logger:
                processor.process()
                self.assertIn('INFO:masu.processor.azure.azure_report_processor', logger.output[0])
                self.assertIn('costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv', logger.output[0])

            for table_name in self.report_tables:
                table = getattr(report_schema, table_name)
                with schema_context(self.schema):
                    count = table.objects.count()
                self.assertTrue(count > counts[table_name])

    def test_azure_process_duplicates(self):
        """Test that row duplicates are not inserted into the DB."""
        counts = {}
        processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.azure_provider_uuid,
        )

        # Process for the first time
        processor.process()
        report_db = self.accessor
        report_schema = report_db.report_schema

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count

        # Wipe stale data
        with schema_context(self.schema):
            self.accessor._get_db_obj_query(AZURE_REPORT_TABLE_MAP['line_item']).delete()

        processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.azure_provider_uuid,
        )
        # Process for the second time
        processor.process()

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            self.assertTrue(count == counts[table_name])

    def test_azure_create_cost_entry_bill(self):
        """Test that a cost entry bill id is returned."""
        table_name = AZURE_REPORT_TABLE_MAP['bill']
        table = getattr(self.report_schema, table_name)
        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        self.assertIsNotNone(bill_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id
        provider_uuid = query.order_by('-id').first().provider_id

        self.assertEqual(bill_id, id_in_db)
        self.assertIsNotNone(provider_uuid)

    def test_azure_create_product(self):
        """Test that a product id is returned."""
        table_name = AZURE_REPORT_TABLE_MAP['product']
        table = getattr(self.report_schema, table_name)
        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.assertIsNotNone(product_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id

        self.assertEqual(product_id, id_in_db)

    def test_azure_create_meter(self):
        """Test that a meter id is returned."""
        table_name = AZURE_REPORT_TABLE_MAP['meter']
        table = getattr(self.report_schema, table_name)
        meter_id = self.processor._create_meter(self.row, self.accessor)

        self.assertIsNotNone(meter_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id

        self.assertEqual(meter_id, id_in_db)

    def test_azure_create_cost_entry_line_item(self):
        """Test that Azure line item data is returned properly."""
        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)
        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)
        meter_id = self.processor._create_meter(self.row, self.accessor)

        self.accessor.commit()

        self.processor._create_cost_entry_line_item(
            self.row,
            bill_id,
            product_id,
            meter_id,
            self.accessor,
        )

        line_item = None
        if self.processor.processed_report.line_items:
            line_item = self.processor.processed_report.line_items[-1]

        self.assertIsNotNone(line_item)
        self.assertIn('tags', line_item)
        self.assertEqual(line_item.get('cost_entry_bill_id'), bill_id)
        self.assertEqual(line_item.get('cost_entry_product_id'), product_id)
        self.assertEqual(line_item.get('meter_id'), meter_id)

        self.assertIsNotNone(self.processor.line_item_columns)

    def test_azure_remove_temp_cur_files(self):
        """Test to remove temporary cost usage files."""
        cur_dir = tempfile.mkdtemp()

        manifest_data = {"assemblyId": "31727a10-f4b4-43a2-80e5-bef1aaeabfc1"}
        manifest = '{}/{}'.format(cur_dir, 'Manifest.json')
        with open(manifest, 'w') as outfile:
            json.dump(manifest_data, outfile)

        file_list = [
            {
                'file': 'costreport_31727a10-f4b4-43a2-80e5-bef1aaeabfc1.csv',
                'processed_date': datetime.datetime(year=2018, month=5, day=3),
            },
            {
                'file': 'costreport_31727a10-f4b4-43a2-80e5-bef1aaeabfc1.csv',
                'processed_date': datetime.datetime(year=2018, month=5, day=3),
            },
            {
                'file': 'costreport_2aeb9169-2526-441c-9eca-d7ed015d52bd.csv',
                'processed_date': datetime.datetime(year=2018, month=5, day=2),
            },
            {
                'file': 'costreport_6c8487e8-c590-4e6a-b2c2-91a2375c0bad.csv',
                'processed_date': datetime.datetime(year=2018, month=5, day=1),
            },
            {
                'file': 'costreport_6c8487e8-c590-4e6a-b2c2-91a2375d0bed.csv',
                'processed_date': None,
            },
        ]
        expected_delete_list = []
        for item in file_list:
            path = '{}/{}'.format(cur_dir, item['file'])
            f = open(path, 'w')
            obj = self.manifest_accessor.get_manifest(self.assembly_id,
                                                      self.azure_provider_uuid)
            with ReportStatsDBAccessor(item['file'], obj.id) as stats:
                stats.update(last_completed_datetime=item['processed_date'])
            f.close()
            if (
                not manifest_data.get('assemblyId') in item['file']
            ):
                expected_delete_list.append(path)
        removed_files = self.processor.remove_temp_cur_files(cur_dir)
        self.assertEqual(sorted(removed_files), sorted(expected_delete_list))
        shutil.rmtree(cur_dir)

    def test_should_process_row_within_cuttoff_date(self):
        """Test that we correctly determine a row should be processed."""
        today = self.date_accessor.today_with_timezone('UTC')
        row = {'UsageDateTime': today.isoformat()}

        processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.azure_provider_uuid,
        )

        should_process = processor._should_process_row(
            row,
            'UsageDateTime',
            False
        )

        self.assertTrue(should_process)

    def test_should_process_row_outside_cuttoff_date(self):
        """Test that we correctly determine a row should be processed."""
        today = self.date_accessor.today_with_timezone('UTC')
        usage_start = today - relativedelta(days=10)
        row = {'UsageDateTime': usage_start.isoformat()}

        processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.azure_provider_uuid,
        )

        should_process = processor._should_process_row(
            row,
            'UsageDateTime',
            False
        )

        self.assertFalse(should_process)
