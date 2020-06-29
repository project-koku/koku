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
"""Processor for Azure Cost Usage Reports."""
import csv
import logging
from datetime import datetime
from os import remove

import pytz
import ujson as json
from dateutil import parser
from django.conf import settings

from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util import common as utils
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDaily
from reporting.provider.azure.models import AzureCostEntryProductService
from reporting.provider.azure.models import AzureMeter

LOG = logging.getLogger(__name__)


class ProcessedAzureReport:
    """Cost usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.bills = {}
        self.products = {}
        self.meters = {}
        self.line_items = []

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.bills = {}
        self.products = {}
        self.meters = {}
        self.line_items = []


class AzureReportProcessor(ReportProcessorBase):
    """Cost Usage Report processor."""

    def __init__(self, schema_name, report_path, compression, provider_uuid, manifest_id=None):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider_uuid=provider_uuid,
            manifest_id=manifest_id,
            processed_report=ProcessedAzureReport(),
        )
        self.table_name = AzureCostEntryLineItemDaily()

        self.manifest_id = manifest_id
        self._report_name = report_path
        self._datetime_format = Config.AZURE_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        self._schema = schema_name

        with AzureReportDBAccessor(self._schema) as report_db:
            self.report_schema = report_db.report_schema
            self.existing_bill_map = report_db.get_cost_entry_bills()
            self.existing_product_map = report_db.get_products()
            self.existing_meter_map = report_db.get_meters()

        self.line_item_columns = None

        stmt = (
            f"Initialized report processor for:\n"
            f" schema_name: {self._schema}\n"
            f" provider_uuid: {provider_uuid}\n"
            f" file: {report_path}"
        )
        LOG.info(stmt)

    def _create_cost_entry_bill(self, row, report_db_accessor):
        """Create a cost entry bill object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A cost entry bill object id

        """
        table_name = AzureCostEntryBill
        row_date = row.get("UsageDateTime")

        report_date_range = utils.month_date_range(parser.parse(row_date))
        start_date, end_date = report_date_range.split("-")

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        key = (start_date_utc, self._provider_uuid)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)

        data["provider_id"] = self._provider_uuid
        data["billing_period_start"] = datetime.strftime(start_date_utc, "%Y-%m-%d %H:%M%z")
        data["billing_period_end"] = datetime.strftime(end_date_utc, "%Y-%m-%d %H:%M%z")

        bill_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name, data, conflict_columns=["billing_period_start", "provider_id"]
        )

        self.processed_report.bills[key] = bill_id

        return bill_id

    def _create_cost_entry_product(self, row, report_db_accessor):
        """Create a cost entry product object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the product object

        """
        table_name = AzureCostEntryProductService
        instance_id = row.get("InstanceId")
        additional_info = row.get("AdditionalInfo")
        service_name = row.get("ServiceName")
        service_tier = row.get("ServiceTier")

        decoded_info = None
        if additional_info:
            decoded_info = json.loads(additional_info)
        instance_type = None
        if decoded_info:
            instance_type = decoded_info.get("ServiceType", None)

        key = (instance_id, instance_type, service_tier, service_name)

        if key in self.processed_report.products:
            return self.processed_report.products[key]

        if key in self.existing_product_map:
            return self.existing_product_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)
        value_set = set(data.values())
        if value_set == {""}:
            return
        data["instance_type"] = instance_type
        data["provider_id"] = self._provider_uuid
        product_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name, data, conflict_columns=["instance_id", "instance_type", "service_tier", "service_name"]
        )
        self.processed_report.products[key] = product_id
        return product_id

    def _create_meter(self, row, report_db_accessor):
        """Create a cost entry product object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the product object

        """
        table_name = AzureMeter
        meter_id = row.get("MeterId")

        key = (meter_id,)

        if key in self.processed_report.meters:
            return self.processed_report.meters[key]

        if key in self.existing_meter_map:
            return self.existing_meter_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)
        value_set = set(data.values())
        if value_set == {""}:
            return
        data["provider_id"] = self._provider_uuid
        meter_id = report_db_accessor.insert_on_conflict_do_nothing(table_name, data, conflict_columns=["meter_id"])
        self.processed_report.meters[key] = meter_id
        return meter_id

    def _create_cost_entry_line_item(self, row, bill_id, product_id, meter_id, report_db_accesor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            bill_id (str): A processed cost entry bill object id
            product_id (str): A processed product object id
            meter_id (str): A processed meter object id

        Returns:
            (None)

        """
        data = self._get_data_for_table(row, self.table_name._meta.db_table)
        tag_str = ""

        if "tags" in data:
            tag_str = data.pop("tags")

        data = report_db_accesor.clean_data(data, self.table_name._meta.db_table)

        data["tags"] = tag_str
        data["cost_entry_bill_id"] = bill_id
        data["cost_entry_product_id"] = product_id
        data["meter_id"] = meter_id

        self.processed_report.line_items.append(data)

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    def create_cost_entry_objects(self, row, report_db_accesor):
        """Create the set of objects required for a row of data."""
        bill_id = self._create_cost_entry_bill(row, report_db_accesor)
        product_id = self._create_cost_entry_product(row, report_db_accesor)
        meter_id = self._create_meter(row, report_db_accesor)

        self._create_cost_entry_line_item(row, bill_id, product_id, meter_id, report_db_accesor)

        return bill_id

    def process(self):
        """Process cost/usage file.

        Returns:
            (None)

        """
        row_count = 0
        is_full_month = self._should_process_full_month()
        self._delete_line_items(AzureReportDBAccessor)
        opener, mode = self._get_file_opener(self._compression)
        with opener(self._report_path, mode, encoding="utf-8-sig") as f:
            with AzureReportDBAccessor(self._schema) as report_db:
                LOG.info("File %s opened for processing", str(f))
                reader = csv.DictReader(f)
                for row in reader:
                    if not self._should_process_row(row, "UsageDateTime", is_full_month):
                        continue
                    self.create_cost_entry_objects(row, report_db)
                    if len(self.processed_report.line_items) >= self._batch_size:
                        LOG.info(
                            "Saving report rows %d to %d for %s",
                            row_count,
                            row_count + len(self.processed_report.line_items),
                            self._report_name,
                        )
                        self._save_to_db(AZURE_REPORT_TABLE_MAP["line_item"], report_db)
                        row_count += len(self.processed_report.line_items)
                        self._update_mappings()

                if self.processed_report.line_items:
                    LOG.info(
                        "Saving report rows %d to %d for %s",
                        row_count,
                        row_count + len(self.processed_report.line_items),
                        self._report_name,
                    )
                    self._save_to_db(AZURE_REPORT_TABLE_MAP["line_item"], report_db)
                    row_count += len(self.processed_report.line_items)

                LOG.info("Completed report processing for file: %s and schema: %s", self._report_name, self._schema)
            if not settings.DEVELOPMENT:
                LOG.info("Removing processed file: %s", self._report_path)
                remove(self._report_path)

            return True

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_product_map.update(self.processed_report.products)
        self.existing_meter_map.update(self.processed_report.meters)

        self.processed_report.remove_processed_rows()
