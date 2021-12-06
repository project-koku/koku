#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for Azure Cost Usage Reports."""
import csv
import logging
from datetime import datetime
from os import remove

import ciso8601
import pytz
import ujson as json
from django.conf import settings
from django.db import transaction

from masu.config import Config
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util import common as utils
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDaily
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureCostEntryProductService
from reporting.provider.azure.models import AzureMeter
from reporting_common import AZURE_REPORT_COLUMNS

LOG = logging.getLogger(__name__)


def normalize_header(header_str):
    """Return the normalized English header column names for Azure."""
    header = header_str.strip("\n").split(",")
    for column in header:
        if column.lower() in AZURE_REPORT_COLUMNS:
            # The header is in English
            return [column.lower() for column in header]
    # Extract the English header values in parenthesis
    return [column.split("(")[1].strip(")").lower() for column in header]


class ProcessedAzureReport:
    """Cost usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.bills = {}
        self.products = {}
        self.meters = {}
        self.requested_partitions = set()
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
        self.table_name = AzureCostEntryLineItemDaily()

        stmt = (
            f"Initialized report processor for:\n"
            f" schema_name: {self._schema}\n"
            f" provider_uuid: {provider_uuid}\n"
            f" file: {report_path}"
        )
        LOG.info(stmt)

    def _process_tags(self, tag_str):
        """Return a JSON string of Azure resource tags.

        Args:
            tag_str (dict): A string for tags from the CSV file

        Returns:
            (str): A JSON string of Azure resource tags

        """
        if "{" in tag_str:
            return tag_str
        elif tag_str == "":
            return "{}"
        tags = tag_str.split('","')
        tag_dict = {}
        for tag in tags:
            key, value = tag.split(": ")
            tag_dict[key.strip('"')] = value.strip('"')

        return json.dumps(tag_dict)

    def _create_cost_entry_bill(self, row, report_db_accessor):
        """Create a cost entry bill object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A cost entry bill object id

        """
        row_date = row.get("usagedatetime")

        report_date_range = utils.month_date_range(ciso8601.parse_datetime(row_date))
        start_date, end_date = report_date_range.split("-")

        start_date_utc = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        key = (start_date_utc, self._provider_uuid)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        data = self._get_data_for_table(row, AzureCostEntryBill._meta.db_table)

        data["provider_id"] = self._provider_uuid
        data["billing_period_start"] = datetime.strftime(start_date_utc, "%Y-%m-%d %H:%M%z")
        data["billing_period_end"] = datetime.strftime(end_date_utc, "%Y-%m-%d %H:%M%z")
        with transaction.atomic():
            bill_id = report_db_accessor.insert_on_conflict_do_nothing(
                AzureCostEntryBill, data, conflict_columns=["billing_period_start", "provider_id"]
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
        instance_id = row.get("instanceid")
        additional_info = row.get("additionalinfo")
        service_name = row.get("servicename")
        service_tier = row.get("servicetier")

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

        data = self._get_data_for_table(row, AzureCostEntryProductService._meta.db_table)
        value_set = set(data.values())
        if value_set == {""}:
            return
        data["instance_type"] = instance_type
        data["provider_id"] = self._provider_uuid
        with transaction.atomic():
            product_id = report_db_accessor.insert_on_conflict_do_nothing(
                AzureCostEntryProductService,
                data,
                conflict_columns=["instance_id", "instance_type", "service_tier", "service_name"],
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
        meter_id = row.get("meterid")

        key = (meter_id,)

        if key in self.processed_report.meters:
            return self.processed_report.meters[key]

        if key in self.existing_meter_map:
            return self.existing_meter_map[key]

        data = self._get_data_for_table(row, AzureMeter._meta.db_table)
        value_set = set(data.values())
        if value_set == {""}:
            return
        data["provider_id"] = self._provider_uuid
        with transaction.atomic():
            meter_pk = report_db_accessor.insert_on_conflict_do_nothing(
                AzureMeter, data, conflict_columns=["meter_id"]
            )
        self.processed_report.meters[key] = meter_pk
        return meter_pk

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
            tag_str = self._process_tags(data.pop("tags"))

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

    def _replace_name_in_header(self, existing_name, new_names, headers):
        """Helper to restore header names to original report format given a list of new name possibilities."""
        modified_header = headers

        if existing_name not in headers:
            other_date_values = new_names
            for other_date in other_date_values:
                if other_date in headers:
                    value_index = modified_header.index(other_date)
                    del modified_header[value_index]
                    modified_header.insert(value_index, existing_name)
                    break
        return modified_header

    def _update_header(self, headers):
        """Update report header to conform with original report format."""
        modified_header = headers

        modified_header = self._replace_name_in_header("usagedatetime", ["date"], modified_header)
        modified_header = self._replace_name_in_header("usagequantity", ["quantity"], modified_header)
        modified_header = self._replace_name_in_header("pretaxcost", ["costinbillingcurrency"], modified_header)
        modified_header = self._replace_name_in_header("instanceid", ["resourceid", "instancename"], modified_header)
        modified_header = self._replace_name_in_header("subscriptionguid", ["subscriptionid"], modified_header)
        modified_header = self._replace_name_in_header("servicename", ["metercategory"], modified_header)

        return modified_header

    def _update_dateformat_in_row(self, row):
        """Convert date format from MM/DD/YYYY to YYYY-MM-DD."""
        modified_row = row
        try:
            modified_row["usagedatetime"] = datetime.strptime(row.get("usagedatetime"), "%m/%d/%Y").strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            LOG.debug("No conversion necessary")
        return modified_row

    def _is_row_unassigned(self, row):
        """Helper to detect unassigned meters in report."""
        if row.get("meterid") == "00000000-0000-0000-0000-000000000000":
            return True
        return False

    def process(self):  # noqa: C901
        """Process cost/usage file.

        Returns:
            (None)

        """
        row_count = 0
        is_full_month = self._should_process_full_month()
        self._delete_line_items(AzureReportDBAccessor)
        opener, mode = self._get_file_opener(self._compression)
        with opener(self._report_path, mode, encoding="utf-8-sig") as f:
            original_header = normalize_header(f.readline())
            header = self._update_header(original_header)

            with AzureReportDBAccessor(self._schema) as report_db:
                temp_table = report_db.create_temp_table(self.table_name._meta.db_table, drop_column="id")
                LOG.info("File %s opened for processing", str(f))
                reader = csv.DictReader(f, fieldnames=header)

                for row in reader:
                    if self._is_row_unassigned(row):
                        continue

                    row = self._update_dateformat_in_row(row)

                    if not self._should_process_row(row, "usagedatetime", is_full_month):
                        continue
                    li_usage_dt = row.get("usagedatetime")
                    if li_usage_dt:
                        try:
                            li_usage_dt = ciso8601.parse_datetime(li_usage_dt).date().replace(day=1)
                        except (ValueError, TypeError):
                            pass  # This is just gathering requested partition start values
                            # If it's invalid, then it's OK to omit storing that value
                            # as it only pertains to a requested partition.
                        else:
                            if li_usage_dt not in self.processed_report.requested_partitions:
                                self.processed_report.requested_partitions.add(li_usage_dt)

                    self.create_cost_entry_objects(row, report_db)
                    if len(self.processed_report.line_items) >= self._batch_size:
                        LOG.info(
                            "Saving report rows %d to %d for %s",
                            row_count,
                            row_count + len(self.processed_report.line_items),
                            self._report_name,
                        )
                        self._save_to_db(temp_table, report_db)
                        row_count += len(self.processed_report.line_items)
                        self._update_mappings()

                if self.processed_report.line_items:
                    LOG.info(
                        "Saving report rows %d to %d for %s",
                        row_count,
                        row_count + len(self.processed_report.line_items),
                        self._report_name,
                    )
                    self._save_to_db(temp_table, report_db)
                    row_count += len(self.processed_report.line_items)

                if self.processed_report.line_items:
                    report_db.merge_temp_table(self.table_name._meta.db_table, temp_table, self.line_item_columns)
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

    def _save_to_db(self, temp_table, report_db):
        # Create any needed partitions
        existing_partitions = report_db.get_existing_partitions(AzureCostEntryLineItemDailySummary)
        report_db.add_partitions(existing_partitions, self.processed_report.requested_partitions)
        # Save batch to DB
        super()._save_to_db(temp_table, report_db)
