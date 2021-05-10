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
"""Processor for GCP Cost Usage Reports."""
import json
import logging
from collections import OrderedDict
from datetime import datetime
from os import path
from os import remove

import ciso8601
import pandas
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction

from api.utils import DateHelper
from masu.config import Config
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItem
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPCostEntryProductService
from reporting.provider.gcp.models import GCPProject

LOG = logging.getLogger(__name__)


class ProcessedGCPReportError(Exception):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


class ProcessedGCPReport:
    """Kept in memory object of report items."""

    def __init__(self):
        """Initialize new cost entry containers."""
        self.line_items = []
        self.bills = {}
        self.projects = {}
        self.products = {}
        self.requested_partitions = set()

    def remove_processed_rows(self):
        """Clear a batch of rows after they've been saved."""
        self.line_items = []
        self.projects = {}
        self.products = {}
        self.bills = {}


class GCPReportProcessor(ReportProcessorBase):
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
            processed_report=ProcessedGCPReport(),
        )
        self._report_name = path.basename(report_path)
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE
        self._manifest_id = manifest_id
        self._provider_uuid = provider_uuid
        self.table_name = GCPCostEntryLineItem()

        self._schema = schema_name

        with GCPReportDBAccessor(self._schema) as report_db:
            self.report_schema = report_db.report_schema
            self.existing_bill_map = report_db.get_cost_entry_bills()
            self.existing_product_map = report_db.get_products()
            self.existing_projects_map = report_db.get_projects()
            self.report_scan_range = report_db.get_gcp_scan_range_from_report_name(report_name=self._report_name)

        self.scan_start = self.report_scan_range.get("start")
        self.scan_end = self.report_scan_range.get("end")
        if not self.scan_start or not self.scan_end:
            err_msg = f"Error recovering start and end date from csv report ({self._report_name})."
            raise ProcessedGCPReportError(err_msg)
        LOG.info("Initialized report processor for file: %s and schema: %s", report_path, self._schema)

        self.line_item_columns = None

    def _delete_line_items_in_range(self, bill_id):
        """Delete stale data between date range."""
        scan_start = ciso8601.parse_datetime(self.scan_start).date()
        scan_end = (ciso8601.parse_datetime(self.scan_end) + relativedelta(days=1)).date()
        gcp_date_filters = {"usage_start__gte": scan_start, "usage_end__lt": scan_end}

        if not self._manifest_id:
            return False
        with ReportManifestDBAccessor() as manifest_accessor:
            num_processed_files = manifest_accessor.number_of_files_processed(self._manifest_id)
            if num_processed_files != 0:
                return False

        with GCPReportDBAccessor(self._schema) as accessor:
            line_item_query = accessor.get_lineitem_query_for_billid(bill_id)
            line_item_query = line_item_query.filter(**gcp_date_filters)
            delete_count = line_item_query.delete()
            if delete_count[0] > 0:
                log_statement = (
                    f"items delted ({delete_count[0]}) for:\n"
                    f" schema_name: {self._schema}\n"
                    f" provider_uuid: {self._provider_uuid}\n"
                    f" bill ID: {bill_id}\n"
                    f" on or after {scan_start}\n"
                    f" before {scan_end}\n"
                )
                LOG.info(log_statement)
        return True

    def _process_tags(self, row):
        """Return a JSON string of GCP tags.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A JSON string of GCP tags

        """
        tags_dict = {}
        labels = row.get("labels", [])
        if isinstance(labels, str):
            labels = json.loads(labels.replace("'", '"'))
        for label in labels:
            key = label["key"]
            value = label["value"]
            tags_dict[key] = value
        return json.dumps(tags_dict)

    def _get_usage_type(self, row):
        """Return usage_type if there is one.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A JSON string of GCP tags

        """
        type_key = "compute.googleapis.com/machine_spec"
        system_labels = row.get("system_labels", [])
        if isinstance(system_labels, str):
            system_labels = json.loads(system_labels.replace("'", '"'))
        for system_label in system_labels:
            key = system_label["key"]
            value = system_label["value"]
            if key == type_key:
                return value
        return None

    def _get_or_create_cost_entry_bill(self, row, report_db_accessor):
        """Get or Create a GCP cost entry bill object.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.

        Returns:
             (string) An id of a GCP Bill.

        """
        table_name = GCPCostEntryBill
        dh = DateHelper()
        invoice_month = row["invoice.month"]
        start_time = dh.gcp_invoice_month_start(invoice_month)
        report_date_range = utils.month_date_range(start_time)
        start_date, end_date = report_date_range.split("-")

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        billing_period_start = datetime.strftime(start_date_utc, "%Y-%m-%d %H:%M%z")

        key = (billing_period_start, self._provider_uuid)
        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        data = {
            "billing_period_start": billing_period_start,
            "billing_period_end": datetime.strftime(end_date_utc, "%Y-%m-%d %H:%M%z"),
            "provider_id": self._provider_uuid,
        }

        key = (start_date_utc, self._provider_uuid)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        with transaction.atomic():
            bill_id = report_db_accessor.insert_on_conflict_do_nothing(
                table_name, data, conflict_columns=["billing_period_start", "provider_id"]
            )
            self.processed_report.bills[key] = bill_id

        return bill_id

    def _get_or_create_gcp_project(self, row, report_db_accessor):
        """Get or Create a GCPProject.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.

        Returns:
             (string) A GCP Project instance id with project_id matching row_id.

        """
        table_name = GCPProject
        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = report_db_accessor.clean_data(data, table_name._meta.db_table)

        key = (data["account_id"], data["project_id"], data["project_name"])
        if key in self.processed_report.projects:
            return self.processed_report.projects[key]

        if key in self.existing_projects_map:
            return self.existing_projects_map[key]

        with transaction.atomic():
            project_id = report_db_accessor.insert_on_conflict_do_update(
                table_name, data, conflict_columns=["project_id"], set_columns=list(data.keys())
            )

        self.processed_report.projects[key] = project_id
        return project_id

    def _get_or_create_gcp_service_product(self, row, report_db_accessor):
        """Get or create service product.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.
            report_db_accessor: accessor class.

        Returns:
            service_product_id (id): Identifier for the Service Product
        """
        table_name = GCPCostEntryProductService
        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = report_db_accessor.clean_data(data, table_name._meta.db_table)

        key = (data["service_id"], data["sku_id"])
        if key in self.processed_report.products:
            return self.processed_report.products[key]

        if key in self.existing_product_map:
            return self.existing_product_map[key]

        with transaction.atomic():
            service_product_id = report_db_accessor.insert_on_conflict_do_nothing(
                table_name, data, conflict_columns=["service_id", "service_alias", "sku_id", "sku_alias"]
            )

        self.processed_report.products[key] = service_product_id
        return service_product_id

    def _create_cost_entry_line_item(self, row, bill_id, project_id, report_db_accessor, service_product_id):
        """Create a cost entry line item object.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row
            bill_id (string): A monthly GCPCostEntryBill
            project_id (string): A GCP Project

        """
        table_name = GCPCostEntryLineItem
        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = report_db_accessor.clean_data(data, table_name._meta.db_table)

        data["cost_entry_bill_id"] = bill_id
        data["project_id"] = project_id
        data["cost_entry_product_id"] = service_product_id
        data["tags"] = self._process_tags(row)
        data["usage_type"] = self._get_usage_type(row)

        li_usage_dt = data.get("usage_start")
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

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

        self.processed_report.line_items.append(data)

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_bill_map.update(self.processed_report.bills)
        self.existing_product_map.update(self.processed_report.products)
        self.existing_projects_map.update(self.processed_report.projects)
        self.processed_report.remove_processed_rows()

    def process(self):
        """Process GCP billing file."""
        row_count = 0

        if not path.exists(self._report_path):
            LOG.info(
                "Skip processing for file: %s and schema: %s as it was not found on disk.",
                self._report_name,
                self._schema,
            )
            return False

        # Read the csv in batched chunks.
        report_csv = pandas.read_csv(self._report_path, chunksize=self._batch_size, compression="infer")

        bills_purged = []
        with GCPReportDBAccessor(self._schema) as report_db:
            temp_table = report_db.create_temp_table(self.table_name._meta.db_table, drop_column="id")
            for chunk in report_csv:

                # Group the information in the csv by the start time and the project id
                report_groups = chunk.groupby(by=["invoice.month", "project.id"])
                for group, rows in report_groups:

                    # Each row in the group contains information that we'll need to create the bill
                    # and the project. Just get the first row to pull this information.
                    first_row = OrderedDict(zip(rows.columns.tolist(), rows.iloc[0].tolist()))

                    bill_id = self._get_or_create_cost_entry_bill(first_row, report_db)
                    if bill_id not in bills_purged:
                        self._delete_line_items_in_range(bill_id)
                        bills_purged.append(bill_id)

                    project_id = self._get_or_create_gcp_project(first_row, report_db)

                    for row in rows.values:
                        processed_row = OrderedDict(zip(rows.columns.tolist(), row.tolist()))
                        service_product_id = self._get_or_create_gcp_service_product(processed_row, report_db)
                        self._create_cost_entry_line_item(
                            processed_row, bill_id, project_id, report_db, service_product_id
                        )
                if self.processed_report.line_items:
                    LOG.info(
                        "Saving report rows %d to %d for %s",
                        row_count,
                        row_count + len(self.processed_report.line_items),
                        self._report_name,
                    )
                    self._save_to_db(temp_table, report_db)
                    row_count += len(self.processed_report.line_items)
                    self._update_mappings()

            if self.line_item_columns:
                report_db.merge_temp_table(self.table_name._meta.db_table, temp_table, self.line_item_columns)

            LOG.info("Completed report processing for file: %s and schema: %s", self._report_name, self._schema)

            if not settings.DEVELOPMENT:
                LOG.info("Removing processed file: %s", self._report_path)
                remove(self._report_path)

        return True

    def _save_to_db(self, temp_table, report_db):
        # Create any needed partitions
        existing_partitions = report_db.get_existing_partitions(GCPCostEntryLineItemDailySummary)
        report_db.add_partitions(existing_partitions, self.processed_report.requested_partitions)
        # Save batch to DB
        super()._save_to_db(temp_table, report_db)
