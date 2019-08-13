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

"""Test the AWSReportProcessor."""
from collections import defaultdict
import csv
import copy
import datetime
from decimal import Decimal
import gzip
from itertools import islice
import json
import logging
import random
import shutil
import tempfile
import psycopg2

from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.test.database.helpers import ReportObjectCreator
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.exceptions import MasuProcessingError
from masu.external import GZIP_COMPRESSED, UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_processor import AWSReportProcessor, ProcessedReport
import masu.util.common as common_util
from masu.test import MasuTestCase


class ProcessedReportTest(MasuTestCase):
    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.report = ProcessedReport()

    def test_remove_processed_rows(self):
        test_entry = {'test': 'entry'}
        self.report.cost_entries.update(test_entry)
        self.report.line_items.append(test_entry)
        self.report.products.update(test_entry)
        self.report.pricing.update(test_entry)
        self.report.reservations.update(test_entry)

        self.report.remove_processed_rows()

        self.assertEqual(self.report.cost_entries, {})
        self.assertEqual(self.report.line_items, [])
        self.assertEqual(self.report.products, {})
        self.assertEqual(self.report.pricing, {})
        self.assertEqual(self.report.reservations, {})


class AWSReportProcessorTest(MasuTestCase):
    """Test Cases for the AWSReportProcessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.test_report = './koku/masu/test/data/test_cur.csv'
        cls.test_report_gzip = './koku/masu/test/data/test_cur.csv.gz'


        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

        with ReportingCommonDBAccessor() as report_common_db:
            cls.column_map = report_common_db.column_map

        _report_tables = copy.deepcopy(AWS_CUR_TABLE_MAP)
        _report_tables.pop('line_item_daily', None)
        _report_tables.pop('line_item_daily_summary', None)
        _report_tables.pop('tags_summary', None)
        cls.report_tables = list(_report_tables.values())
        # Grab a single row of test data to work with
        with open(cls.test_report, 'r') as f:
            reader = csv.DictReader(f)
            cls.row = next(reader)

    def setUp(self):
        super().setUp()

        self.processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )

        billing_start = self.date_accessor.today_with_timezone('UTC').replace(
            year=2018, month=6, day=1, hour=0, minute=0, second=0
        )
        self.assembly_id = '1234'
        self.manifest_dict = {
            'assembly_id': self.assembly_id,
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_id': self.aws_provider.id,
        }

        self.accessor = AWSReportDBAccessor(self.schema, self.column_map)
        self.report_schema = self.accessor.report_schema
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()

    def tearDown(self):
        """Return the database to a pre-test state."""
        super().tearDown()

        self.processor.processed_report.remove_processed_rows()
        self.processor.line_item_columns = None

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.processor._schema_name)
        self.assertIsNotNone(self.processor._report_path)
        self.assertIsNotNone(self.processor._report_name)
        self.assertIsNotNone(self.processor._compression)
        self.assertEqual(
            self.processor._datetime_format, Config.AWS_DATETIME_STR_FORMAT
        )
        self.assertEqual(
            self.processor._batch_size, Config.REPORT_PROCESSING_BATCH_SIZE
        )

    def test_initializer_unsupported_compression(self):
        """Assert that an error is raised for an invalid compression."""
        with self.assertRaises(MasuProcessingError):
            AWSReportProcessor(
                schema_name=self.schema,
                report_path=self.test_report,
                compression='unsupported',
                provider_id=self.aws_provider.id,
            )

    def test_process_default(self):
        """Test the processing of an uncompressed file."""
        counts = {}
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
            manifest_id=self.manifest.id,
        )
        report_db = self.accessor
        report_schema = report_db.report_schema
        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count

        bill_date = self.manifest.billing_period_start_datetime.date()
        expected = f'INFO:masu.processor.aws.aws_report_processor:Deleting data for schema: acct10001 and bill date: {bill_date}'
        logging.disable(
            logging.NOTSET
        )  # We are currently disabling all logging below CRITICAL in masu/__init__.py
        with self.assertLogs(
            'masu.processor.aws.aws_report_processor', level='INFO'
        ) as logger:
            processor.process()
            self.assertIn(expected, logger.output)

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()

            if table_name in (
                'reporting_awscostentryreservation',
                'reporting_ocpawscostlineitem_daily_summary',
                'reporting_ocpawscostlineitem_project_daily_summary',
            ):
                self.assertTrue(count >= counts[table_name])
            else:
                self.assertTrue(count > counts[table_name])

    def test_process_gzip(self):
        """Test the processing of a gzip compressed file."""
        counts = {}
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report_gzip,
            compression=GZIP_COMPRESSED,
            provider_id=self.aws_provider.id,
        )
        report_db = self.accessor
        report_schema = report_db.report_schema
        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count

        processor.process()

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()

            if table_name in (
                'reporting_awscostentryreservation',
                'reporting_ocpawscostlineitem_daily_summary',
                'reporting_ocpawscostlineitem_project_daily_summary',
            ):
                self.assertTrue(count >= counts[table_name])
            else:
                self.assertTrue(count > counts[table_name])

    def test_process_duplicates(self):
        """Test that row duplicates are not inserted into the DB."""
        counts = {}
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
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
            self.accessor._get_db_obj_query(AWS_CUR_TABLE_MAP['line_item']).delete()

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )
        # Process for the second time
        processor.process()

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            self.assertTrue(count == counts[table_name])

    def test_process_finalized_rows(self):
        """Test that a finalized bill is processed properly."""
        data = []
        table_name = AWS_CUR_TABLE_MAP['line_item']

        with open(self.test_report, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row['bill/InvoiceId'] = '12345'

        tmp_file = '/tmp/test_process_finalized_rows.csv'
        field_names = data[0].keys()

        with open(tmp_file, 'w') as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )

        # Process for the first time
        processor.process()
        report_db = self.accessor
        report_schema = report_db.report_schema

        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        bill_table = getattr(report_schema, bill_table_name)
        with schema_context(self.schema):
            bill = bill_table.objects.first()
            self.assertIsNone(bill.finalized_datetime)

        table = getattr(report_schema, table_name)
        with schema_context(self.schema):
            orig_count = table.objects.count()

        # Wipe stale data
        with schema_context(self.schema):
            self.accessor._get_db_obj_query(table_name).delete()

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )
        # Process for the second time
        processor.process()

        with schema_context(self.schema):
            count = table.objects.count()
            self.assertTrue(count == orig_count)
            count = table.objects.filter(invoice_id__isnull=False).count()
            self.assertTrue(count == orig_count)

        with schema_context(self.schema):
            bill = bill_table.objects.first()
            self.assertIsNotNone(bill.finalized_datetime)

    def test_process_finalized_rows_small_batch_size(self):
        """Test that a finalized bill is processed properly on batch size."""
        data = []
        table_name = AWS_CUR_TABLE_MAP['line_item']

        with open(self.test_report, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row['bill/InvoiceId'] = '12345'

        tmp_file = '/tmp/test_process_finalized_rows.csv'
        field_names = data[0].keys()

        with open(tmp_file, 'w') as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )

        # Process for the first time
        processor.process()
        report_db = self.accessor
        report_schema = report_db.report_schema

        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        bill_table = getattr(report_schema, bill_table_name)
        with schema_context(self.schema):
            bill = bill_table.objects.first()
            self.assertIsNone(bill.finalized_datetime)

        table = getattr(report_schema, table_name)
        with schema_context(self.schema):
            orig_count = table.objects.count()

        # Wipe stale data
        with schema_context(self.schema):
            self.accessor._get_db_obj_query(table_name).delete()

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )
        processor._batch_size = 2
        # Process for the second time
        processor.process()

        with schema_context(self.schema):
            count = table.objects.count()
            self.assertTrue(count == orig_count)
            count = table.objects.filter(invoice_id__isnull=False).count()
            self.assertTrue(count == orig_count)

        with schema_context(self.schema):
            bill = bill_table.objects.first()
            self.assertIsNotNone(bill.finalized_datetime)

    def test_do_not_overwrite_finalized_bill_timestamp(self):
        """Test that a finalized bill timestamp does not get overwritten."""
        data = []
        with open(self.test_report, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row['bill/InvoiceId'] = '12345'

        tmp_file = '/tmp/test_process_finalized_rows.csv'
        field_names = data[0].keys()

        with open(tmp_file, 'w') as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )

        # Process for the first time
        processor.process()
        report_db = self.accessor
        report_schema = report_db.report_schema

        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        bill_table = getattr(report_schema, bill_table_name)
        with schema_context(self.schema):
            bill = bill_table.objects.first()

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )
        # Process for the second time
        processor.process()

        finalized_datetime = bill.finalized_datetime

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )
        # Process for the third time to make sure the timestamp is the same
        processor.process()
        self.assertEqual(bill.finalized_datetime, finalized_datetime)

    def test_get_file_opener_default(self):
        """Test that the default file opener is returned."""
        opener, mode = self.processor._get_file_opener(UNCOMPRESSED)

        self.assertEqual(opener, open)
        self.assertEqual(mode, 'r')

    def test_get_file_opener_gzip(self):
        """Test that the gzip file opener is returned."""
        opener, mode = self.processor._get_file_opener(GZIP_COMPRESSED)

        self.assertEqual(opener, gzip.open)
        self.assertEqual(mode, 'rt')

    def test_update_mappings(self):
        """Test that mappings are updated."""
        test_entry = {'key': 'value'}
        counts = {}
        ce_maps = {
            'cost_entry': self.processor.existing_cost_entry_map,
            'product': self.processor.existing_product_map,
            'pricing': self.processor.existing_pricing_map,
            'reservation': self.processor.existing_reservation_map,
        }

        for name, ce_map in ce_maps.items():
            counts[name] = len(ce_map.values())
            ce_map.update(test_entry)

        self.processor._update_mappings()

        for name, ce_map in ce_maps.items():
            self.assertTrue(len(ce_map.values()) > counts[name])
            for key in test_entry:
                self.assertIn(key, ce_map)

    def test_write_processed_rows_to_csv(self):
        """Test that the CSV bulk upload file contains proper data."""
        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)
        cost_entry_id = self.processor._create_cost_entry(
            self.row, bill_id, self.accessor
        )
        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)
        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)
        reservation_id = self.processor._create_cost_entry_reservation(
            self.row, self.accessor
        )
        self.processor._create_cost_entry_line_item(
            self.row,
            cost_entry_id,
            bill_id,
            product_id,
            pricing_id,
            reservation_id,
            self.accessor,
        )

        file_obj = self.processor._write_processed_rows_to_csv()

        line_item_data = self.processor.processed_report.line_items.pop()
        # Convert data to CSV format
        expected_values = [
            str(value) if value else None for value in line_item_data.values()
        ]

        reader = csv.reader(file_obj)
        new_row = next(reader)
        new_row = new_row[0].split('\t')
        actual = {}

        for i, key in enumerate(line_item_data.keys()):
            actual[key] = new_row[i] if new_row[i] else None

        self.assertEqual(actual.keys(), line_item_data.keys())
        self.assertEqual(list(actual.values()), expected_values)

    def test_get_data_for_table(self):
        """Test that a row is disected into appropriate data structures."""
        column_map = self.column_map

        for table_name in self.report_tables:
            expected_columns = sorted(column_map[table_name].values())
            data = self.processor._get_data_for_table(self.row, table_name)

            for key in data:
                self.assertIn(key, expected_columns)

    def test_process_tags(self):
        """Test that tags are properly packaged in a JSON string."""
        row = {
            'resourceTags/user:environment': 'prod',
            'notATag': 'value',
            'resourceTags/System': 'value',
            'resourceTags/system:system_key': 'system_value',
        }
        expected = {'environment': 'prod', 'system_key': 'system_value'}
        actual = json.loads(self.processor._process_tags(row))

        self.assertNotIn(row['notATag'], actual)
        self.assertEqual(expected, actual)

    def test_get_cost_entry_time_interval(self):
        """Test that an interval string is properly split."""
        fmt = Config.AWS_DATETIME_STR_FORMAT
        end = datetime.datetime.utcnow()
        expected_start = (end - datetime.timedelta(days=1)).strftime(fmt)
        expected_end = end.strftime(fmt)
        interval = expected_start + '/' + expected_end

        actual_start, actual_end = self.processor._get_cost_entry_time_interval(
            interval
        )

        self.assertEqual(expected_start, actual_start)
        self.assertEqual(expected_end, actual_end)

    def test_create_cost_entry_bill(self):
        """Test that a cost entry bill id is returned."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        table = getattr(self.report_schema, table_name)

        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        self.assertIsNotNone(bill_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id
        provider_id = query.order_by('-id').first().provider_id

        self.assertEqual(bill_id, id_in_db)
        self.assertIsNotNone(provider_id)

    def test_create_cost_entry_bill_existing(self):
        """Test that a cost entry bill id is returned from an existing bill."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        table = getattr(self.report_schema, table_name)

        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        query = self.accessor._get_db_obj_query(table_name)
        bill = query.first()

        self.processor.current_bill = bill

        new_bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        self.assertEqual(bill_id, new_bill_id)

        self.processor.current_bill = None

    def test_create_cost_entry(self):
        """Test that a cost entry id is returned."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        table = getattr(self.report_schema, table_name)


        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        cost_entry_id = self.processor._create_cost_entry(
            self.row, bill_id, self.accessor
        )
        self.accessor.commit()

        self.assertIsNotNone(cost_entry_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id

        self.assertEqual(cost_entry_id, id_in_db)

    def test_create_cost_entry_existing(self):
        """Test that a cost entry id is returned from an existing entry."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        table = getattr(self.report_schema, table_name)

        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)
        self.accessor.commit()

        interval = self.row.get('identity/TimeInterval')
        start, _ = self.processor._get_cost_entry_time_interval(interval)
        key = (bill_id, start)
        expected_id = random.randint(1, 9)
        self.processor.existing_cost_entry_map[key] = expected_id

        cost_entry_id = self.processor._create_cost_entry(
            self.row, bill_id, self.accessor
        )
        self.assertEqual(cost_entry_id, expected_id)

    def test_create_cost_entry_line_item(self):
        """Test that line item data is returned properly."""
        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)
        cost_entry_id = self.processor._create_cost_entry(
            self.row, bill_id, self.accessor
        )
        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)
        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)
        reservation_id = self.processor._create_cost_entry_reservation(
            self.row, self.accessor
        )

        self.accessor.commit()

        self.processor._create_cost_entry_line_item(
            self.row,
            cost_entry_id,
            bill_id,
            product_id,
            pricing_id,
            reservation_id,
            self.accessor,
        )

        line_item = None
        if self.processor.processed_report.line_items:
            line_item = self.processor.processed_report.line_items[-1]

        self.assertIsNotNone(line_item)
        self.assertIn('tags', line_item)
        self.assertEqual(line_item.get('cost_entry_id'), cost_entry_id)
        self.assertEqual(line_item.get('cost_entry_bill_id'), bill_id)
        self.assertEqual(line_item.get('cost_entry_product_id'), product_id)
        self.assertEqual(line_item.get('cost_entry_pricing_id'), pricing_id)
        self.assertEqual(line_item.get('cost_entry_reservation_id'), reservation_id)

        self.assertIsNotNone(self.processor.line_item_columns)

    def test_create_cost_entry_product(self):
        """Test that a cost entry product id is returned."""
        table_name = AWS_CUR_TABLE_MAP['product']
        table = getattr(self.report_schema, table_name)


        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.accessor.commit()

        self.assertIsNotNone(product_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id

        self.assertEqual(product_id, id_in_db)

    def test_create_cost_entry_product_already_processed(self):
        """Test that an already processed product id is returned."""
        expected_id = random.randint(1, 9)
        sku = self.row.get('product/sku')
        product_name = self.row.get('product/ProductName')
        region = self.row.get('product/region')
        key = (sku, product_name, region)
        self.processor.processed_report.products.update({key: expected_id})

        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.assertEqual(product_id, expected_id)

    def test_create_cost_entry_product_existing(self):
        """Test that a previously existing product id is returned."""
        expected_id = random.randint(1, 9)
        sku = self.row.get('product/sku')
        product_name = self.row.get('product/ProductName')
        region = self.row.get('product/region')
        key = (sku, product_name, region)
        self.processor.existing_product_map.update({key: expected_id})

        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.assertEqual(product_id, expected_id)

    def test_create_cost_entry_pricing(self):
        """Test that a cost entry pricing id is returned."""
        table_name = AWS_CUR_TABLE_MAP['pricing']
        table = getattr(self.report_schema, table_name)


        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)

        self.accessor.commit()

        self.assertIsNotNone(pricing_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id

        self.assertEqual(pricing_id, id_in_db)

    def test_create_cost_entry_pricing_already_processed(self):
        """Test that an already processed pricing id is returned."""
        expected_id = random.randint(1, 9)

        key = '{term}-{unit}'.format(
            term=self.row['pricing/term'], unit=self.row['pricing/unit']
        )
        self.processor.processed_report.pricing.update({key: expected_id})

        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)

        self.assertEqual(pricing_id, expected_id)

    def test_create_cost_entry_pricing_existing(self):
        """Test that a previously existing pricing id is returned."""
        expected_id = random.randint(1, 9)

        key = '{term}-{unit}'.format(
            term=self.row['pricing/term'], unit=self.row['pricing/unit']
        )
        self.processor.existing_pricing_map.update({key: expected_id})

        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)

        self.assertEqual(pricing_id, expected_id)

    def test_create_cost_entry_reservation(self):
        """Test that a cost entry reservation id is returned."""
        # Ensure a reservation exists on the row
        arn = 'TestARN'
        row = copy.deepcopy(self.row)
        row['reservation/ReservationARN'] = arn

        table_name = AWS_CUR_TABLE_MAP['reservation']
        table = getattr(self.report_schema, table_name)


        reservation_id = self.processor._create_cost_entry_reservation(
            row, self.accessor
        )

        self.accessor.commit()

        self.assertIsNotNone(reservation_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by('-id').first().id

        self.assertEqual(reservation_id, id_in_db)

    def test_create_cost_entry_reservation_update(self):
        """Test that a cost entry reservation id is returned."""
        # Ensure a reservation exists on the row
        arn = 'TestARN'
        row = copy.deepcopy(self.row)
        row['reservation/ReservationARN'] = arn
        row['reservation/NumberOfReservations'] = 1

        table_name = AWS_CUR_TABLE_MAP['reservation']
        table = getattr(self.report_schema, table_name)

        reservation_id = self.processor._create_cost_entry_reservation(
            row, self.accessor
        )

        self.accessor.commit()

        self.assertIsNotNone(reservation_id)

        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(table_name)
            id_in_db = query.order_by('-id').first().id

        self.assertEqual(reservation_id, id_in_db)

        row['lineItem/LineItemType'] = 'RIFee'
        res_count = row['reservation/NumberOfReservations']
        row['reservation/NumberOfReservations'] = res_count + 1
        reservation_id = self.processor._create_cost_entry_reservation(
            row, self.accessor
        )
        self.accessor.commit()

        self.assertEqual(reservation_id, id_in_db)

        db_row = query.filter(id=id_in_db).first()
        self.assertEqual(
            db_row.number_of_reservations, row['reservation/NumberOfReservations']
        )

    def test_create_cost_entry_reservation_already_processed(self):
        """Test that an already processed reservation id is returned."""
        expected_id = random.randint(1, 9)
        arn = self.row.get('reservation/ReservationARN')
        self.processor.processed_report.reservations.update({arn: expected_id})

        reservation_id = self.processor._create_cost_entry_reservation(
            self.row, self.accessor
        )

        self.assertEqual(reservation_id, expected_id)

    def test_create_cost_entry_reservation_existing(self):
        """Test that a previously existing reservation id is returned."""
        expected_id = random.randint(1, 9)
        arn = self.row.get('reservation/ReservationARN')
        self.processor.existing_reservation_map.update({arn: expected_id})

        product_id = self.processor._create_cost_entry_reservation(
            self.row, self.accessor
        )

        self.assertEqual(product_id, expected_id)

    def test_remove_temp_cur_files(self):
        """Test to remove temporary cost usage files."""
        cur_dir = tempfile.mkdtemp()

        manifest_data = {"assemblyId": "6e019de5-a41d-4cdb-b9a0-99bfba9a9cb5"}
        manifest = '{}/{}'.format(cur_dir, 'koku-Manifest.json')
        with open(manifest, 'w') as outfile:
            json.dump(manifest_data, outfile)

        file_list = [
            {
                'file': '6e019de5-a41d-4cdb-b9a0-99bfba9a9cb5-koku-1.csv.gz',
                'processed_date': datetime.datetime(year=2018, month=5, day=3),
            },
            {
                'file': '6e019de5-a41d-4cdb-b9a0-99bfba9a9cb5-koku-2.csv.gz',
                'processed_date': datetime.datetime(year=2018, month=5, day=3),
            },
            {
                'file': '2aeb9169-2526-441c-9eca-d7ed015d52bd-koku-1.csv.gz',
                'processed_date': datetime.datetime(year=2018, month=5, day=2),
            },
            {
                'file': '6c8487e8-c590-4e6a-b2c2-91a2375c0bad-koku-1.csv.gz',
                'processed_date': datetime.datetime(year=2018, month=5, day=1),
            },
            {
                'file': '6c8487e8-c590-4e6a-b2c2-91a2375d0bed-koku-1.csv.gz',
                'processed_date': None,
            },
        ]
        expected_delete_list = []
        for item in file_list:
            path = '{}/{}'.format(cur_dir, item['file'])
            f = open(path, 'w')
            obj = self.manifest_accessor.get_manifest(self.assembly_id,
                                                      self.aws_provider.id)
            with ReportStatsDBAccessor(item['file'], obj.id) as stats:
                stats.update(last_completed_datetime=item['processed_date'])
            f.close()
            if (
                not item['file'].startswith(manifest_data.get('assemblyId'))
                and item['processed_date']
            ):
                expected_delete_list.append(path)

        removed_files = self.processor.remove_temp_cur_files(cur_dir)
        self.assertEqual(sorted(removed_files), sorted(expected_delete_list))
        shutil.rmtree(cur_dir)

    def test_check_for_finalized_bill_bill_is_finalized(self):
        """Verify that a file with invoice_id is marked as finalzed."""
        data = []
        table_name = AWS_CUR_TABLE_MAP['line_item']

        with open(self.test_report, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row['bill/InvoiceId'] = '12345'

        tmp_file = '/tmp/test_process_finalized_rows.csv'
        field_names = data[0].keys()

        with open(tmp_file, 'w') as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )

        result = processor._check_for_finalized_bill()

        self.assertTrue(result)

    def test_check_for_finalized_bill_bill_not_finalized(self):
        """Verify that a file without invoice_id is not marked as finalzed."""

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )

        result = processor._check_for_finalized_bill()

        self.assertFalse(result)

    def test_delete_line_items_success(self):
        """Test that data is deleted before processing a manifest."""
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
            manifest_id=self.manifest.id,
        )
        processor.process()
        result = processor._delete_line_items()

        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills()
            for bill_id in bills.values():
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                self.assertTrue(result)
                self.assertEqual(line_item_query.count(), 0)

    def test_delete_line_items_not_first_file_in_manifest(self):
        """Test that data is not deleted once a file has been processed."""
        self.manifest.num_processed_files = 1
        self.manifest.save()
        self.manifest_accessor.commit()
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
            manifest_id=self.manifest.id,
        )
        processor.process()
        result = processor._delete_line_items()
        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills()
            for bill_id in bills.values():
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                self.assertFalse(result)
                self.assertNotEqual(line_item_query.count(), 0)

    def test_delete_line_items_no_manifest(self):
        """Test that no data is deleted without a manifest id."""
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.aws_provider.id,
        )
        processor.process()
        result = processor._delete_line_items()
        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills()
            for bill_id in bills.values():
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                self.assertFalse(result)
                self.assertNotEqual(line_item_query.count(), 0)
