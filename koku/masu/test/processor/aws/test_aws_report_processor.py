#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportProcessor."""
import copy
import csv
import datetime
import gzip
import json
import logging
import os
import random
import shutil
import tempfile
from unittest.mock import Mock
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.db.models import Max
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.exceptions import MasuProcessingError
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_processor import AWSReportProcessor
from masu.processor.aws.aws_report_processor import ProcessedReport
from masu.test import MasuTestCase
from masu.test.database.helpers import ManifestCreationHelper
from reporting_common import REPORT_COLUMN_MAP
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class ProcessedReportTest(MasuTestCase):
    """Test cases for Processed Reports."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.report = ProcessedReport()

    def test_remove_processed_rows(self):
        """Test that remove_processed_rows removes rows."""
        test_entry = {"test": "entry"}
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
        cls.test_report_test_path = "./koku/masu/test/data/test_cur.csv"
        cls.test_report_gzip_test_path = "./koku/masu/test/data/test_cur.csv.gz"

        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

        _report_tables = copy.deepcopy(AWS_CUR_TABLE_MAP)
        _report_tables.pop("line_item_daily", None)
        _report_tables.pop("line_item_daily_summary", None)
        _report_tables.pop("tags_summary", None)
        _report_tables.pop("enabled_tag_keys", None)
        _report_tables.pop("ocp_on_aws_tags_summary", None)
        cls.report_tables = list(_report_tables.values())
        # Grab a single row of test data to work with
        with open(cls.test_report_test_path, "r") as f:
            reader = csv.DictReader(f)
            cls.row = next(reader)

    def setUp(self):
        """Set up shared variables."""
        super().setUp()

        self.temp_dir = tempfile.mkdtemp()
        self.test_report = f"{self.temp_dir}/test_cur.csv"
        self.test_report_gzip = f"{self.temp_dir}/test_cur.csv.gz"

        shutil.copy2(self.test_report_test_path, self.test_report)
        shutil.copy2(self.test_report_gzip_test_path, self.test_report_gzip)

        self.processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        billing_start = self.date_accessor.today_with_timezone("UTC").replace(
            year=2018, month=6, day=1, hour=0, minute=0, second=0
        )
        self.assembly_id = "1234"
        self.manifest_dict = {
            "assembly_id": self.assembly_id,
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }

        self.accessor = AWSReportDBAccessor(self.schema)
        self.report_schema = self.accessor.report_schema
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    def tearDown(self):
        """Return the database to a pre-test state."""
        super().tearDown()

        shutil.rmtree(self.temp_dir)

        self.processor.processed_report.remove_processed_rows()
        self.processor.line_item_columns = None

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.processor._schema)
        self.assertIsNotNone(self.processor._report_path)
        self.assertIsNotNone(self.processor._report_name)
        self.assertIsNotNone(self.processor._compression)
        self.assertEqual(self.processor._datetime_format, Config.AWS_DATETIME_STR_FORMAT)
        self.assertEqual(self.processor._batch_size, Config.REPORT_PROCESSING_BATCH_SIZE)

    def test_initializer_unsupported_compression(self):
        """Assert that an error is raised for an invalid compression."""
        with self.assertRaises(MasuProcessingError):
            AWSReportProcessor(
                schema_name=self.schema,
                report_path=self.test_report,
                compression="unsupported",
                provider_uuid=self.aws_provider_uuid,
            )

    def test_process_default(self):
        """Test the processing of an uncompressed file."""
        counts = {}
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
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

        expected = (
            f"INFO:masu.processor.report_processor_base:Processing bill starting on {bill_date}.\n"
            f" Processing entire month.\n"
            f" schema_name: {self.schema},\n"
            f" provider_uuid: {self.aws_provider_uuid},\n"
            f" manifest_id: {self.manifest.id}"
        )
        logging.disable(logging.NOTSET)  # We are currently disabling all logging below CRITICAL in masu/__init__.py
        with self.assertLogs("masu.processor.report_processor_base", level="INFO") as logger:
            processor.process()
            self.assertIn(expected, logger.output)

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()

            if table_name in (
                "reporting_awscostentryreservation",
                "reporting_awscostentrypricing",
                "reporting_ocpawscostlineitem_daily_summary",
                "reporting_ocpawscostlineitem_project_daily_summary",
            ):
                self.assertTrue(count >= counts[table_name])
            else:
                self.assertTrue(count > counts[table_name])

        self.assertFalse(os.path.exists(self.test_report))

    def test_process_no_file_on_disk(self):
        """Test the processing of when the file is not found on disk."""
        counts = {}
        base_name = "test_no_cur.csv"
        no_report = f"{self.temp_dir}/{base_name}"
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=no_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )
        report_db = self.accessor
        report_schema = report_db.report_schema
        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count

        expected = (
            "INFO:masu.processor.aws.aws_report_processor:"
            f"Skip processing for file: {base_name} and "
            f"schema: {self.schema} as it was not found on disk."
        )
        logging.disable(logging.NOTSET)  # We are currently disabling all logging below CRITICAL in masu/__init__.py
        with self.assertLogs("masu.processor.aws.aws_report_processor", level="INFO") as logger:
            processor.process()
            self.assertIn(expected, logger.output)

    def test_process_gzip(self):
        """Test the processing of a gzip compressed file."""
        counts = {}
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report_gzip,
            compression=GZIP_COMPRESSED,
            provider_uuid=self.aws_provider_uuid,
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
                "reporting_awscostentryreservation",
                "reporting_ocpawscostlineitem_daily_summary",
                "reporting_ocpawscostlineitem_project_daily_summary",
                "reporting_awscostentrypricing",
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
            provider_uuid=self.aws_provider_uuid,
        )

        report_db = self.accessor
        report_schema = report_db.report_schema
        with schema_context(self.schema):
            table_name = AWS_CUR_TABLE_MAP["line_item"]
            table = getattr(report_schema, table_name)
            initial_line_item_count = table.objects.count()

        # Process for the first time
        processor.process()

        for table_name in self.report_tables:
            table = getattr(report_schema, table_name)
            with schema_context(self.schema):
                count = table.objects.count()
            counts[table_name] = count
            if table_name == AWS_CUR_TABLE_MAP["line_item"]:
                counts[table_name] = counts[table_name] - initial_line_item_count

        # Wipe stale data
        with schema_context(self.schema):
            self.accessor._get_db_obj_query(AWS_CUR_TABLE_MAP["line_item"]).delete()

        shutil.copy2(self.test_report_test_path, self.test_report)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
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
        table_name = AWS_CUR_TABLE_MAP["line_item"]

        with open(self.test_report, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row["bill/InvoiceId"] = "12345"

        tmp_file = "/tmp/test_process_finalized_rows.csv"
        field_names = data[0].keys()

        with open(tmp_file, "w") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        report_db = self.accessor
        report_schema = report_db.report_schema
        with schema_context(self.schema):
            table = getattr(report_schema, table_name)
            initial_line_item_count = table.objects.count()

        # Process for the first time
        processor.process()

        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
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
            provider_uuid=self.aws_provider_uuid,
        )
        # Process for the second time
        processor.process()

        with schema_context(self.schema):
            count = table.objects.count()
            self.assertTrue(count == orig_count - initial_line_item_count)
            count = table.objects.filter(invoice_id__isnull=False).count()
            self.assertTrue(count == orig_count - initial_line_item_count)

        with schema_context(self.schema):
            final_count = bill_table.objects.filter(finalized_datetime__isnull=False).count()
            self.assertEqual(final_count, 1)

    def test_process_finalized_rows_small_batch_size(self):
        """Test that a finalized bill is processed properly on batch size."""
        data = []
        table_name = AWS_CUR_TABLE_MAP["line_item"]

        with open(self.test_report, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row["bill/InvoiceId"] = "12345"

        tmp_file = "/tmp/test_process_finalized_rows.csv"
        field_names = data[0].keys()

        with open(tmp_file, "w") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        report_db = self.accessor
        report_schema = report_db.report_schema
        table = getattr(report_schema, table_name)
        with schema_context(self.schema):
            initial_line_item_count = table.objects.count()

        # Process for the first time
        processor.process()

        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
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
            provider_uuid=self.aws_provider_uuid,
        )
        processor._batch_size = 2
        # Process for the second time
        processor.process()

        with schema_context(self.schema):
            count = table.objects.count()
            self.assertTrue(count == orig_count - initial_line_item_count)
            count = table.objects.filter(invoice_id__isnull=False).count()
            self.assertTrue(count == orig_count - initial_line_item_count)

        with schema_context(self.schema):
            final_count = bill_table.objects.filter(finalized_datetime__isnull=False).count()
            self.assertEqual(final_count, 1)

    def test_do_not_overwrite_finalized_bill_timestamp(self):
        """Test that a finalized bill timestamp does not get overwritten."""
        data = []
        with open(self.test_report, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row["bill/InvoiceId"] = "12345"

        tmp_file = "/tmp/test_process_finalized_rows.csv"
        field_names = data[0].keys()

        with open(tmp_file, "w") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        # Process for the first time
        processor.process()
        report_db = self.accessor
        report_schema = report_db.report_schema

        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
        bill_table = getattr(report_schema, bill_table_name)
        with schema_context(self.schema):
            bill = bill_table.objects.first()

        with open(tmp_file, "w") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )
        # Process for the second time
        processor.process()

        finalized_datetime = bill.finalized_datetime

        with open(tmp_file, "w") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )
        # Process for the third time to make sure the timestamp is the same
        processor.process()
        self.assertEqual(bill.finalized_datetime, finalized_datetime)

    def test_get_file_opener_default(self):
        """Test that the default file opener is returned."""
        opener, mode = self.processor._get_file_opener(UNCOMPRESSED)

        self.assertEqual(opener, open)
        self.assertEqual(mode, "r")

    def test_get_file_opener_gzip(self):
        """Test that the gzip file opener is returned."""
        opener, mode = self.processor._get_file_opener(GZIP_COMPRESSED)

        self.assertEqual(opener, gzip.open)
        self.assertEqual(mode, "rt")

    def test_update_mappings(self):
        """Test that mappings are updated."""
        test_entry = {"key": "value"}
        counts = {}
        ce_maps = {
            "cost_entry": self.processor.existing_cost_entry_map,
            "product": self.processor.existing_product_map,
            "pricing": self.processor.existing_pricing_map,
            "reservation": self.processor.existing_reservation_map,
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
        cost_entry_id = self.processor._create_cost_entry(self.row, bill_id, self.accessor)
        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)
        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)
        reservation_id = self.processor._create_cost_entry_reservation(self.row, self.accessor)
        self.processor._create_cost_entry_line_item(
            self.row, cost_entry_id, bill_id, product_id, pricing_id, reservation_id, self.accessor
        )

        file_obj = self.processor._write_processed_rows_to_csv()

        line_item_data = self.processor.processed_report.line_items.pop()
        # Convert data to CSV format
        expected_values = [str(value) if value else None for value in line_item_data.values()]

        reader = csv.reader(file_obj)
        new_row = next(reader)
        actual = {}
        for i, key in enumerate(line_item_data.keys()):
            actual[key] = new_row[i] if new_row[i] else None

        self.assertEqual(actual.keys(), line_item_data.keys())
        self.assertEqual(list(actual.values()), expected_values)

    def test_get_data_for_table(self):
        """Test that a row is disected into appropriate data structures."""

        for table_name in self.report_tables:
            expected_columns = sorted(REPORT_COLUMN_MAP[table_name].values())
            data = self.processor._get_data_for_table(self.row, table_name)

            for key in data:
                self.assertIn(key, expected_columns)

    def test_process_tags(self):
        """Test that tags are properly packaged in a JSON string."""
        row = {
            "resourceTags/user:environment": "prod",
            "notATag": "value",
            "resourceTags/System": "value",
            "resourceTags/system:system_key": "system_value",
        }
        expected = {"environment": "prod"}
        actual = json.loads(self.processor._process_tags(row))

        self.assertNotIn(row["notATag"], actual)
        self.assertEqual(expected, actual)

    def test_get_cost_entry_time_interval(self):
        """Test that an interval string is properly split."""
        fmt = Config.AWS_DATETIME_STR_FORMAT
        end = datetime.datetime.utcnow()
        expected_start = (end - datetime.timedelta(days=1)).strftime(fmt)
        expected_end = end.strftime(fmt)
        interval = expected_start + "/" + expected_end

        actual_start, actual_end = self.processor._get_cost_entry_time_interval(interval)

        self.assertEqual(expected_start, actual_start)
        self.assertEqual(expected_end, actual_end)

    def test_create_cost_entry_bill(self):
        """Test that a cost entry bill id is returned."""
        table_name = AWS_CUR_TABLE_MAP["bill"]

        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        self.assertIsNotNone(bill_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by("-id").first().id
        provider_uuid = query.order_by("-id").first().provider_id

        self.assertEqual(bill_id, id_in_db)
        self.assertIsNotNone(provider_uuid)

    def test_create_cost_entry_bill_existing(self):
        """Test that a cost entry bill id is returned from an existing bill."""
        table_name = AWS_CUR_TABLE_MAP["bill"]

        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        query = self.accessor._get_db_obj_query(table_name)
        bill = query.first()

        self.processor.current_bill = bill

        new_bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        self.assertEqual(bill_id, new_bill_id)

        self.processor.current_bill = None

    def test_create_cost_entry(self):
        """Test that a cost entry id is returned."""
        table_name = AWS_CUR_TABLE_MAP["cost_entry"]

        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        cost_entry_id = self.processor._create_cost_entry(self.row, bill_id, self.accessor)

        self.assertIsNotNone(cost_entry_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by("-id").first().id

        self.assertEqual(cost_entry_id, id_in_db)

    def test_create_cost_entry_existing(self):
        """Test that a cost entry id is returned from an existing entry."""
        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)

        interval = self.row.get("identity/TimeInterval")
        start, _ = self.processor._get_cost_entry_time_interval(interval)
        key = (bill_id, start)
        expected_id = random.randint(1, 9)
        self.processor.existing_cost_entry_map[key] = expected_id

        cost_entry_id = self.processor._create_cost_entry(self.row, bill_id, self.accessor)
        self.assertEqual(cost_entry_id, expected_id)

    def test_create_cost_entry_line_item(self):
        """Test that line item data is returned properly."""
        bill_id = self.processor._create_cost_entry_bill(self.row, self.accessor)
        cost_entry_id = self.processor._create_cost_entry(self.row, bill_id, self.accessor)
        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)
        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)
        reservation_id = self.processor._create_cost_entry_reservation(self.row, self.accessor)

        self.processor._create_cost_entry_line_item(
            self.row, cost_entry_id, bill_id, product_id, pricing_id, reservation_id, self.accessor
        )

        line_item = None
        if self.processor.processed_report.line_items:
            line_item = self.processor.processed_report.line_items[-1]

        self.assertIsNotNone(line_item)
        self.assertIn("tags", line_item)
        self.assertEqual(line_item.get("cost_entry_id"), cost_entry_id)
        self.assertEqual(line_item.get("cost_entry_bill_id"), bill_id)
        self.assertEqual(line_item.get("cost_entry_product_id"), product_id)
        self.assertEqual(line_item.get("cost_entry_pricing_id"), pricing_id)
        self.assertEqual(line_item.get("cost_entry_reservation_id"), reservation_id)

        self.assertIsNotNone(self.processor.line_item_columns)

    def test_create_cost_entry_product(self):
        """Test that a cost entry product id is returned."""
        table_name = AWS_CUR_TABLE_MAP["product"]

        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.assertIsNotNone(product_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by("-id").first().id

        self.assertEqual(product_id, id_in_db)

    def test_create_cost_entry_product_already_processed(self):
        """Test that an already processed product id is returned."""
        expected_id = random.randint(1, 9)
        sku = self.row.get("product/sku")
        product_name = self.row.get("product/ProductName")
        region = self.row.get("product/region")
        key = (sku, product_name, region)
        self.processor.processed_report.products.update({key: expected_id})

        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.assertEqual(product_id, expected_id)

    def test_create_cost_entry_product_existing(self):
        """Test that a previously existing product id is returned."""
        expected_id = random.randint(1, 9)
        sku = self.row.get("product/sku")
        product_name = self.row.get("product/ProductName")
        region = self.row.get("product/region")
        key = (sku, product_name, region)
        self.processor.existing_product_map.update({key: expected_id})

        product_id = self.processor._create_cost_entry_product(self.row, self.accessor)

        self.assertEqual(product_id, expected_id)

    def test_create_cost_entry_pricing(self):
        """Test that a cost entry pricing id is returned."""
        table_name = AWS_CUR_TABLE_MAP["pricing"]

        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)

        self.assertIsNotNone(pricing_id)

        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(table_name)
            id_in_db = query.order_by("-id").first().id
            self.assertEqual(pricing_id, id_in_db)

    def test_create_cost_entry_pricing_already_processed(self):
        """Test that an already processed pricing id is returned."""
        expected_id = random.randint(1, 9)

        key = "{term}-{unit}".format(term=self.row["pricing/term"], unit=self.row["pricing/unit"])
        self.processor.processed_report.pricing.update({key: expected_id})

        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)

        self.assertEqual(pricing_id, expected_id)

    def test_create_cost_entry_pricing_existing(self):
        """Test that a previously existing pricing id is returned."""
        expected_id = random.randint(1, 9)

        key = "{term}-{unit}".format(term=self.row["pricing/term"], unit=self.row["pricing/unit"])
        self.processor.existing_pricing_map.update({key: expected_id})

        pricing_id = self.processor._create_cost_entry_pricing(self.row, self.accessor)

        self.assertEqual(pricing_id, expected_id)

    def test_create_cost_entry_reservation(self):
        """Test that a cost entry reservation id is returned."""
        # Ensure a reservation exists on the row
        arn = "TestARN"
        row = copy.deepcopy(self.row)
        row["reservation/ReservationARN"] = arn

        table_name = AWS_CUR_TABLE_MAP["reservation"]

        reservation_id = self.processor._create_cost_entry_reservation(row, self.accessor)

        self.assertIsNotNone(reservation_id)

        query = self.accessor._get_db_obj_query(table_name)
        id_in_db = query.order_by("-id").first().id

        self.assertEqual(reservation_id, id_in_db)

    def test_create_cost_entry_reservation_update(self):
        """Test that a cost entry reservation id is returned."""
        # Ensure a reservation exists on the row
        arn = "TestARN"
        row = copy.deepcopy(self.row)
        row["reservation/ReservationARN"] = arn
        row["reservation/NumberOfReservations"] = 1

        table_name = AWS_CUR_TABLE_MAP["reservation"]

        reservation_id = self.processor._create_cost_entry_reservation(row, self.accessor)

        self.assertIsNotNone(reservation_id)

        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(table_name)
            id_in_db = query.order_by("-id").first().id

        self.assertEqual(reservation_id, id_in_db)

        row["lineItem/LineItemType"] = "RIFee"
        res_count = row["reservation/NumberOfReservations"]
        row["reservation/NumberOfReservations"] = res_count + 1
        reservation_id = self.processor._create_cost_entry_reservation(row, self.accessor)

        self.assertEqual(reservation_id, id_in_db)

        db_row = query.filter(id=id_in_db).first()
        self.assertEqual(db_row.number_of_reservations, row["reservation/NumberOfReservations"])

    def test_create_cost_entry_reservation_already_processed(self):
        """Test that an already processed reservation id is returned."""
        expected_id = random.randint(1, 9)
        arn = self.row.get("reservation/ReservationARN")
        self.processor.processed_report.reservations.update({arn: expected_id})

        reservation_id = self.processor._create_cost_entry_reservation(self.row, self.accessor)

        self.assertEqual(reservation_id, expected_id)

    def test_create_cost_entry_reservation_existing(self):
        """Test that a previously existing reservation id is returned."""
        expected_id = random.randint(1, 9)
        arn = self.row.get("reservation/ReservationARN")
        self.processor.existing_reservation_map.update({arn: expected_id})

        product_id = self.processor._create_cost_entry_reservation(self.row, self.accessor)

        self.assertEqual(product_id, expected_id)

    def test_check_for_finalized_bill_bill_is_finalized(self):
        """Verify that a file with invoice_id is marked as finalzed."""
        data = []

        with open(self.test_report, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        for row in data:
            row["bill/InvoiceId"] = "12345"

        tmp_file = "/tmp/test_process_finalized_rows.csv"
        field_names = data[0].keys()

        with open(tmp_file, "w") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(data)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        result = processor._check_for_finalized_bill()

        self.assertTrue(result)

    def test_check_for_finalized_bill_bill_not_finalized(self):
        """Verify that a file without invoice_id is not marked as finalzed."""
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        result = processor._check_for_finalized_bill()

        self.assertFalse(result)

    def test_check_for_finalized_bill_empty_bill(self):
        """Verify that an empty file is not marked as finalzed."""
        tmp_file = "/tmp/test_process_finalized_rows.csv"

        with open(tmp_file, "w"):
            pass

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=tmp_file,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )
        result = processor._check_for_finalized_bill()
        self.assertFalse(result)

    def test_delete_line_items_success(self):
        """Test that data is deleted before processing a manifest."""
        manifest = CostUsageReportManifest.objects.filter(
            provider__uuid=self.aws_provider_uuid, billing_period_start_datetime=DateHelper().this_month_start
        ).first()
        CostUsageReportStatus.objects.filter(manifest_id=manifest.id).delete()
        bill_date = manifest.billing_period_start_datetime
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=manifest.id,
        )

        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills_by_date(bill_date)
            bill_ids = [bill.id for bill in bills]

        for bill_id in bill_ids:
            with schema_context(self.schema):
                before_count = self.accessor.get_lineitem_query_for_billid(bill_id).count()
            result = processor._delete_line_items(AWSReportDBAccessor)

            with schema_context(self.schema):
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                self.assertTrue(result)
                self.assertLess(line_item_query.count(), before_count)

    def test_delete_line_items_not_first_file_in_manifest(self):
        """Test that data is not deleted once a file has been processed."""
        manifest_helper = ManifestCreationHelper(
            self.manifest.id, self.manifest.num_total_files, self.manifest.assembly_id
        )

        report_file = manifest_helper.generate_one_test_file()
        manifest_helper.mark_report_file_as_completed(report_file)

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )
        processor.process()
        result = processor._delete_line_items(AWSReportDBAccessor)
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
            provider_uuid=self.aws_provider_uuid,
        )
        processor.process()
        result = processor._delete_line_items(AWSReportDBAccessor)
        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills()
            for bill_id in bills.values():
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                self.assertFalse(result)
                self.assertNotEqual(line_item_query.count(), 0)

    @patch("masu.processor.report_processor_base.ReportProcessorBase._should_process_full_month")
    def test_delete_line_items_use_data_cutoff_date(self, mock_should_process):
        """Test that only three days of data are deleted."""
        mock_should_process.return_value = True

        today = self.date_accessor.today_with_timezone("UTC").replace(hour=0, minute=0, second=0, microsecond=0)
        first_of_month = today.replace(day=1)

        self.manifest.billing_period_start_datetime = first_of_month
        self.manifest.save()

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path="",
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        # Get latest data date.
        bill_ids = []
        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills()
            for key, value in bills.items():
                if key[1] == DateHelper().this_month_start:
                    bill_ids.append(value)

        for bill_id in bill_ids:
            with schema_context(self.schema):
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                undeleted_max_date = line_item_query.aggregate(max_date=Max("usage_start"))

            mock_should_process.return_value = False
            processor._delete_line_items(AWSReportDBAccessor, is_finalized=False)

            with schema_context(self.schema):
                # bills = self.accessor.get_cost_entry_bills()
                # for bill_id in bills.values():
                line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
                if today.day <= 3:
                    self.assertEqual(line_item_query.count(), 0)
                else:
                    max_date = line_item_query.aggregate(max_date=Max("usage_start"))
                    self.assertLess(max_date.get("max_date").date(), processor.data_cutoff_date)
                    self.assertLess(max_date.get("max_date").date(), undeleted_max_date.get("max_date").date())
                    self.assertNotEqual(line_item_query.count(), 0)

    @patch("masu.processor.report_processor_base.DateAccessor")
    def test_data_cutoff_date_not_start_of_month(self, mock_date):
        """Test that the data_cuttof_date respects month boundaries."""
        today = self.date_accessor.today_with_timezone("UTC").replace(day=10)
        expected = today.date() - relativedelta(days=2)

        mock_date.return_value.today_with_timezone.return_value = today

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )
        self.assertEqual(expected, processor.data_cutoff_date)

    @patch("masu.processor.report_processor_base.DateAccessor")
    def test_data_cutoff_date_start_of_month(self, mock_date):
        """Test that the data_cuttof_date respects month boundaries."""
        today = self.date_accessor.today_with_timezone("UTC")
        first_of_month = today.replace(day=1)

        mock_date.return_value.today_with_timezone.return_value = first_of_month

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )
        self.assertEqual(first_of_month.date(), processor.data_cutoff_date)

    @patch("masu.processor.report_processor_base.ReportManifestDBAccessor")
    def test_should_process_full_month_first_manifest_for_bill(self, mock_manifest_accessor):
        """Test that we process data for a new bill/manifest completely."""
        mock_manifest = Mock()
        today = self.date_accessor.today_with_timezone("UTC")
        mock_manifest.billing_period_start_datetime = today
        mock_manifest.num_processed_files = 1
        mock_manifest.num_total_files = 2
        mock_manifest_accessor.return_value.__enter__.return_value.get_manifest_by_id.return_value = mock_manifest
        mock_manifest_accessor.return_value.__enter__.return_value.get_manifest_list_for_provider_and_bill_date.return_value = [  # noqa
            mock_manifest
        ]
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        self.assertTrue(processor._should_process_full_month())

    @patch("masu.processor.report_processor_base.ReportManifestDBAccessor")
    def test_should_process_full_month_not_first_manifest_for_bill(self, mock_manifest_accessor):
        """Test that we process a window of data for the bill/manifest."""
        mock_manifest = Mock()
        today = self.date_accessor.today_with_timezone("UTC")
        mock_manifest.billing_period_start_datetime = today
        mock_manifest.num_processed_files = 1
        mock_manifest.num_total_files = 1
        mock_manifest_accessor.return_value.__enter__.return_value.get_manifest_by_id.return_value = mock_manifest
        mock_manifest_accessor.return_value.__enter__.return_value.get_manifest_list_for_provider_and_bill_date.return_value = [  # noqa
            mock_manifest,
            mock_manifest,
        ]
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        self.assertFalse(processor._should_process_full_month())

    @patch("masu.processor.report_processor_base.ReportManifestDBAccessor")
    def test_should_process_full_month_manifest_for_not_current_month(self, mock_manifest_accessor):
        """Test that we process this manifest completely."""
        mock_manifest = Mock()
        last_month = self.date_accessor.today_with_timezone("UTC") - relativedelta(months=1)
        mock_manifest.billing_period_start_datetime = last_month
        mock_manifest_accessor.return_value.__enter__.return_value.get_manifest_by_id.return_value = mock_manifest
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        self.assertTrue(processor._should_process_full_month())

    def test_should_process_full_month_no_manifest(self):
        """Test that we process this manifest completely."""
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
        )

        self.assertTrue(processor._should_process_full_month())

    def test_should_process_row_within_cuttoff_date(self):
        """Test that we correctly determine a row should be processed."""
        today = self.date_accessor.today_with_timezone("UTC")
        row = {"lineItem/UsageStartDate": today.isoformat()}

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        should_process = processor._should_process_row(row, "lineItem/UsageStartDate", False)

        self.assertTrue(should_process)

    def test_should_process_row_outside_cuttoff_date(self):
        """Test that we correctly determine a row should be processed."""
        today = self.date_accessor.today_with_timezone("UTC")
        usage_start = today - relativedelta(days=10)
        row = {"lineItem/UsageStartDate": usage_start.isoformat()}

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        should_process = processor._should_process_row(row, "lineItem/UsageStartDate", False)

        self.assertFalse(should_process)

    def test_should_process_is_full_month(self):
        """Test that we correctly determine a row should be processed."""
        today = self.date_accessor.today_with_timezone("UTC")
        usage_start = today - relativedelta(days=10)
        row = {"lineItem/UsageStartDate": usage_start.isoformat()}

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        should_process = processor._should_process_row(row, "lineItem/UsageStartDate", True)

        self.assertTrue(should_process)

    def test_should_process_is_finalized(self):
        """Test that we correctly determine a row should be processed."""
        today = self.date_accessor.today_with_timezone("UTC")
        usage_start = today - relativedelta(days=10)
        row = {"lineItem/UsageStartDate": usage_start.isoformat()}

        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )

        should_process = processor._should_process_row(row, "lineItem/UsageStartDate", False, is_finalized=True)

        self.assertTrue(should_process)

    def test_get_date_column_filter(self):
        """Test that the Azure specific filter is returned."""
        processor = AWSReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=self.manifest.id,
        )
        date_filter = processor.get_date_column_filter()

        self.assertIn("usage_start__gte", date_filter)

    def test_process_memory_value(self):
        """Test that product data has memory properly parsed."""

        data = {"memory": None}
        result = self.processor._process_memory_value(data)
        self.assertIsNone(result.get("memory"))
        self.assertIsNone(result.get("memory_unit"))

        data = {"memory": "NA"}
        result = self.processor._process_memory_value(data)
        self.assertIsNone(result.get("memory"))
        self.assertIsNone(result.get("memory_unit"))

        data = {"memory": "4GiB"}
        result = self.processor._process_memory_value(data)
        self.assertEqual(result.get("memory"), 4)
        self.assertEqual(result.get("memory_unit"), "GiB")

        data = {"memory": "4 GB"}
        result = self.processor._process_memory_value(data)
        self.assertEqual(result.get("memory"), 4)
        self.assertEqual(result.get("memory_unit"), "GB")

        data = {"memory": "4"}
        result = self.processor._process_memory_value(data)
        self.assertEqual(result.get("memory"), 4)
        self.assertIsNone(result.get("memory_unit"))
