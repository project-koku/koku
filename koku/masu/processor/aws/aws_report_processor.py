#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for Cost Usage Reports."""
import csv
import json
import logging
from os import path
from os import remove

import ciso8601
from django.conf import settings
from django.db import transaction

from masu.config import Config
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util.common import split_alphanumeric_string
from reporting.provider.aws.models import AWSCostEntry
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItem
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryPricing
from reporting.provider.aws.models import AWSCostEntryProduct
from reporting.provider.aws.models import AWSCostEntryReservation
from reporting_common import REPORT_COLUMN_MAP

LOG = logging.getLogger(__name__)


class ProcessedReport:
    """Cost usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.bills = {}
        self.cost_entries = {}
        self.line_items = []
        self.products = {}
        self.reservations = {}
        self.pricing = {}
        self.requested_partitions = set()

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.bills = {}
        self.cost_entries = {}
        self.line_items = []
        self.products = {}
        self.reservations = {}
        self.pricing = {}


class AWSReportProcessor(ReportProcessorBase):
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
            processed_report=ProcessedReport(),
        )

        self.manifest_id = manifest_id
        self._report_name = path.basename(report_path)
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        # Gather database accessors

        with AWSReportDBAccessor(self._schema) as report_db:
            self.report_schema = report_db.report_schema
            self.existing_bill_map = report_db.get_cost_entry_bills()
            self.existing_cost_entry_map = report_db.get_cost_entries()
            self.existing_product_map = report_db.get_products()
            self.existing_pricing_map = report_db.get_pricing()
            self.existing_reservation_map = report_db.get_reservations()

        self.line_item_columns = None
        self.table_name = AWSCostEntryLineItem()
        stmt = (
            f"Initialized report processor for:\n"
            f" schema_name: {self._schema}\n"
            f" provider_uuid: {provider_uuid}\n"
            f" file: {self._report_name}"
        )
        LOG.info(stmt)

    def process(self):  # noqa: C901
        """Process CUR file.

        Returns:
            (None)

        """
        row_count = 0
        opener, mode = self._get_file_opener(self._compression)

        if not path.exists(self._report_path):
            LOG.info(
                "Skip processing for file: %s and schema: %s as it was not found on disk.",
                self._report_name,
                self._schema,
            )
            return False

        is_finalized_data = self._check_for_finalized_bill()
        is_full_month = self._should_process_full_month()
        self._delete_line_items(AWSReportDBAccessor, is_finalized=is_finalized_data)
        opener, mode = self._get_file_opener(self._compression)
        with opener(self._report_path, mode) as f:
            with AWSReportDBAccessor(self._schema) as report_db:
                temp_table = report_db.create_temp_table(self.table_name._meta.db_table, drop_column="id")
                LOG.info("File %s opened for processing", str(f))
                reader = csv.DictReader(f)
                for row in reader:
                    # If this isn't an initial load and it isn't finalized data
                    # we should only process recent data.
                    if not self._should_process_row(
                        row, "lineItem/UsageStartDate", is_full_month, is_finalized=is_finalized_data
                    ):
                        continue

                    li_usage_dt = row.get("lineItem/UsageStartDate")
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

                    bill_id = self.create_cost_entry_objects(row, report_db)
                    if len(self.processed_report.line_items) >= self._batch_size:
                        LOG.debug(
                            "Saving report rows %d to %d for %s",
                            row_count,
                            row_count + len(self.processed_report.line_items),
                            self._report_name,
                        )
                        self._save_to_db(temp_table, report_db)

                        row_count += len(self.processed_report.line_items)
                        self._update_mappings()

                if self.processed_report.line_items:
                    LOG.debug(
                        "Saving report rows %d to %d for %s",
                        row_count,
                        row_count + len(self.processed_report.line_items),
                        self._report_name,
                    )
                    self._save_to_db(temp_table, report_db)

                    row_count += len(self.processed_report.line_items)

                if is_finalized_data:
                    report_db.mark_bill_as_finalized(bill_id)

                if self.processed_report.line_items:
                    report_db.merge_temp_table(self.table_name._meta.db_table, temp_table, self.line_item_columns)

        LOG.info("Completed report processing for file: %s and schema: %s", self._report_name, self._schema)

        if not settings.DEVELOPMENT:
            LOG.info("Removing processed file: %s", self._report_path)
            remove(self._report_path)

        return is_finalized_data

    def _check_for_finalized_bill(self):
        """Read one line of the report file to check for finalization.

        Returns:
            (Boolean): Whether the bill is finalized

        """
        opener, mode = self._get_file_opener(self._compression)
        with opener(self._report_path, mode) as f:
            reader = csv.DictReader(f)
            for row in reader:
                invoice_id = row.get("bill/InvoiceId")
                return invoice_id is not None and invoice_id != ""
            return False

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_cost_entry_map.update(self.processed_report.cost_entries)
        self.existing_product_map.update(self.processed_report.products)
        self.existing_pricing_map.update(self.processed_report.pricing)
        self.existing_reservation_map.update(self.processed_report.reservations)

        self.processed_report.remove_processed_rows()

    def _process_memory_value(self, data):
        """Parse out value and unit from memory strings."""
        if "memory" in data and data["memory"] is not None:
            unit = None
            try:
                memory = float(data["memory"])
            except ValueError:
                memory = None
                # Memory can come as a single number or a number with a unit
                # e.g. "1", "1GB", "1 Gb" so it gets special cased.
                memory_list = list(split_alphanumeric_string(data["memory"]))
                if memory_list:
                    memory = memory_list[0]
                    if len(memory_list) > 1:
                        unit = memory_list[1]
            try:
                memory = float(memory)
            except (ValueError, TypeError):
                memory = None
                unit = None
            data["memory"] = memory
            data["memory_unit"] = unit
        return data

    def _get_data_for_table(self, row, table_name):
        """Extract the data from a row for a specific table.

        Args:
            row (dict): A dictionary representation of a CSV file row
            table_name (str): The DB table fields are required for

        Returns:
            (dict): The data from the row keyed on the DB table's column names

        """
        column_map = REPORT_COLUMN_MAP[table_name]

        return {column_map[key]: value for key, value in row.items() if key in column_map}

    def _process_tags(self, row, tag_prefix="resourceTags/user"):
        """Return a JSON string of AWS resource tags.

        Args:
            row (dict): A dictionary representation of a CSV file row
            tag_prefix (str): A specifier used to identify a value as a tag

        Returns:
            (str): A JSON string of AWS resource tags

        """
        tag_dict = {}
        for key, value in row.items():
            if tag_prefix in key and row[key]:
                key_value = key.split(":")
                if len(key_value) > 1:
                    tag_dict[key_value[-1]] = value
        return json.dumps(tag_dict)

    def _get_cost_entry_time_interval(self, interval):
        """Split the cost entry time interval into start and end.

        Args:
            interval (str): The time interval from the cost usage report.

        Returns:
            (str, str): Separated start and end strings

        """
        start, end = interval.split("/")
        return start, end

    def _create_cost_entry_bill(self, row, report_db_accessor):
        """Create a cost entry bill object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A cost entry bill object id

        """
        table_name = AWSCostEntryBill
        start_date = row.get("bill/BillingPeriodStartDate")
        bill_type = row.get("bill/BillType")
        payer_account_id = row.get("bill/PayerAccountId")

        key = (bill_type, payer_account_id, start_date, self._provider_uuid)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)

        data["provider_id"] = self._provider_uuid

        with transaction.atomic():
            bill_id = report_db_accessor.insert_on_conflict_do_nothing(
                table_name,
                data,
                conflict_columns=["bill_type", "payer_account_id", "billing_period_start", "provider_id"],
            )

        self.processed_report.bills[key] = bill_id

        return bill_id

    def _create_cost_entry(self, row, bill_id, report_db_accessor):
        """Create a cost entry object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            bill_id (str): The current cost entry bill id

        Returns:
            (str): The DB id of the cost entry object

        """
        table_name = AWSCostEntry
        interval = row.get("identity/TimeInterval")
        start, end = self._get_cost_entry_time_interval(interval)

        key = (bill_id, start)
        if key in self.processed_report.cost_entries:
            return self.processed_report.cost_entries[key]

        if key in self.existing_cost_entry_map:
            return self.existing_cost_entry_map[key]

        data = {"bill_id": bill_id, "interval_start": start, "interval_end": end}
        with transaction.atomic():
            cost_entry_id = report_db_accessor.insert_on_conflict_do_nothing(table_name, data)
        self.processed_report.cost_entries[key] = cost_entry_id

        return cost_entry_id

    def _create_cost_entry_line_item(
        self, row, cost_entry_id, bill_id, product_id, pricing_id, reservation_id, report_db_accesor
    ):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            cost_entry_id (str): A processed cost entry object id
            bill_id (str): A processed cost entry bill object id
            product_id (str): A processed product object id
            pricing_id (str): A processed pricing object id
            reservation_id (str): A processed reservation object id

        Returns:
            (None)

        """
        table_name = AWSCostEntryLineItem
        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = report_db_accesor.clean_data(data, table_name._meta.db_table)

        data["tags"] = self._process_tags(row)
        data["cost_entry_id"] = cost_entry_id
        data["cost_entry_bill_id"] = bill_id
        data["cost_entry_product_id"] = product_id
        data["cost_entry_pricing_id"] = pricing_id
        data["cost_entry_reservation_id"] = reservation_id

        self.processed_report.line_items.append(data)

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    def _create_cost_entry_pricing(self, row, report_db_accessor):
        """Create a cost entry pricing object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the pricing object

        """
        table_name = AWSCostEntryPricing

        term = row.get("pricing/term") if row.get("pricing/term") else "None"
        unit = row.get("pricing/unit") if row.get("pricing/unit") else "None"

        key = f"{term}-{unit}"
        if key in self.processed_report.pricing:
            return self.processed_report.pricing[key]

        if key in self.existing_pricing_map:
            return self.existing_pricing_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)
        value_set = set(data.values())
        if value_set == {""}:
            return

        with transaction.atomic():
            pricing_id = report_db_accessor.insert_on_conflict_do_nothing(table_name, data)
        self.processed_report.pricing[key] = pricing_id

        return pricing_id

    def _create_cost_entry_product(self, row, report_db_accessor):
        """Create a cost entry product object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the product object

        """
        table_name = AWSCostEntryProduct
        sku = row.get("product/sku")
        product_name = row.get("product/ProductName")
        region = row.get("product/region")
        key = (sku, product_name, region)

        if key in self.processed_report.products:
            return self.processed_report.products[key]

        if key in self.existing_product_map:
            return self.existing_product_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = self._process_memory_value(data)
        value_set = set(data.values())
        if value_set == {""}:
            return
        with transaction.atomic():
            product_id = report_db_accessor.insert_on_conflict_do_nothing(
                table_name, data, conflict_columns=["sku", "product_name", "region"]
            )
        self.processed_report.products[key] = product_id
        return product_id

    def _create_cost_entry_reservation(self, row, report_db_accessor):
        """Create a cost entry reservation object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the reservation object

        """
        table_name = AWSCostEntryReservation
        arn = row.get("reservation/ReservationARN")
        line_item_type = row.get("lineItem/LineItemType", "").lower()
        reservation_id = None

        if arn in self.processed_report.reservations:
            reservation_id = self.processed_report.reservations.get(arn)
        elif arn in self.existing_reservation_map:
            reservation_id = self.existing_reservation_map[arn]

        if reservation_id is None or line_item_type == "rifee":
            data = self._get_data_for_table(row, table_name._meta.db_table)
            value_set = set(data.values())
            if value_set == {""}:
                return
        else:
            return reservation_id

        # Special rows with additional reservation information
        with transaction.atomic():
            if line_item_type == "rifee":
                reservation_id = report_db_accessor.insert_on_conflict_do_update(
                    table_name, data, conflict_columns=["reservation_arn"], set_columns=list(data.keys())
                )
            else:
                reservation_id = report_db_accessor.insert_on_conflict_do_nothing(
                    table_name, data, conflict_columns=["reservation_arn"]
                )
        self.processed_report.reservations[arn] = reservation_id

        return reservation_id

    def create_cost_entry_objects(self, row, report_db_accesor):
        """Create the set of objects required for a row of data."""
        bill_id = self._create_cost_entry_bill(row, report_db_accesor)
        cost_entry_id = self._create_cost_entry(row, bill_id, report_db_accesor)
        product_id = self._create_cost_entry_product(row, report_db_accesor)
        pricing_id = self._create_cost_entry_pricing(row, report_db_accesor)
        reservation_id = self._create_cost_entry_reservation(row, report_db_accesor)

        self._create_cost_entry_line_item(
            row, cost_entry_id, bill_id, product_id, pricing_id, reservation_id, report_db_accesor
        )

        return bill_id

    def _save_to_db(self, temp_table, report_db):
        # Create any needed partitions
        existing_partitions = report_db.get_existing_partitions(AWSCostEntryLineItemDailySummary)
        report_db.add_partitions(existing_partitions, self.processed_report.requested_partitions)
        # Save batch to DB
        super()._save_to_db(temp_table, report_db)
