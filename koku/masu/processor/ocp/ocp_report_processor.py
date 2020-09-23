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
"""Processor for OCP Usage Reports."""
import csv
import json
import logging
from os import path
from os import remove

import ciso8601
from django.conf import settings
from django.db import transaction

from masu.config import Config
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util.ocp import common as utils
from reporting.provider.ocp.models import OCPNodeLabelLineItem
from reporting.provider.ocp.models import OCPStorageLineItem
from reporting.provider.ocp.models import OCPUsageLineItem
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReport
from reporting.provider.ocp.models import OCPUsageReportPeriod


LOG = logging.getLogger(__name__)


class OCPReportProcessorError(Exception):
    """OCPReportProcessor Error."""


class ProcessedOCPReport:
    """Usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.report_periods = {}
        self.reports = {}
        self.line_items = []
        self.line_item_keys = {}
        self.requested_partitions = set()

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.report_periods = {}
        self.reports = {}
        self.line_items = []


class OCPReportProcessor:
    """OCP Usage Report processor."""

    def __init__(self, schema_name, report_path, compression, provider_uuid):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        self._processor = None
        _, self.report_type = utils.detect_type(report_path)
        if self.report_type == utils.OCPReportTypes.CPU_MEM_USAGE:
            self._processor = OCPCpuMemReportProcessor(schema_name, report_path, compression, provider_uuid)
        elif self.report_type == utils.OCPReportTypes.STORAGE:
            self._processor = OCPStorageProcessor(schema_name, report_path, compression, provider_uuid)
        elif self.report_type == utils.OCPReportTypes.NODE_LABELS:
            self._processor = OCPNodeLabelProcessor(schema_name, report_path, compression, provider_uuid)
        elif self.report_type == utils.OCPReportTypes.UNKNOWN:
            raise OCPReportProcessorError("Unknown OCP report type.")

    def process(self):
        """Process report file."""
        return self._processor.process()

    def remove_temp_cur_files(self, report_path):
        """Process temporary files."""
        return self._processor.remove_temp_cur_files(report_path)


class OCPReportProcessorBase(ReportProcessorBase):
    """Base class for OCP report processing."""

    def __init__(self, schema_name, report_path, compression, provider_uuid):
        """Initialize base class."""
        super().__init__(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider_uuid=provider_uuid,
            manifest_id=None,
            processed_report=ProcessedOCPReport(),
        )

        self._report_name = path.basename(report_path)
        self._cluster_id = utils.get_cluster_id_from_provider(provider_uuid)
        self._cluster_alias = utils.get_cluster_alias_from_cluster_id(self._cluster_id)

        self._datetime_format = Config.OCP_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        with OCPReportDBAccessor(self._schema) as report_db:
            self.existing_report_periods_map = report_db.get_report_periods()
            self.existing_report_map = report_db.get_reports()

        self.line_item_columns = None

    def _create_report(self, row, report_period_id, report_db_accessor):
        """Create a report object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): report period object id

        Returns:
            (str): The DB id of the report object

        """
        table_name = OCPUsageReport
        start = ciso8601.parse_datetime(row.get("interval_start").replace(" +0000 UTC", "+0000"))
        end = ciso8601.parse_datetime(row.get("interval_end").replace(" +0000 UTC", "+0000"))

        key = (report_period_id, start)
        if key in self.processed_report.reports:
            return self.processed_report.reports[key]

        if key in self.existing_report_map:
            return self.existing_report_map[key]

        data = {"report_period_id": report_period_id, "interval_start": start, "interval_end": end}
        with transaction.atomic():
            report_id = report_db_accessor.insert_on_conflict_do_nothing(
                table_name, data, conflict_columns=["report_period_id", "interval_start"]
            )

        self.processed_report.reports[key] = report_id

        return report_id

    def _create_report_period(self, row, cluster_id, report_db_accessor, cluster_alias):
        """Create a report period object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            cluster_id (str): cluster ID
            cluster_alias (str): cluster alias

        Returns:
            (str): The DB id of the report period object

        """
        table_name = OCPUsageReportPeriod
        start = ciso8601.parse_datetime(row.get("report_period_start").replace(" +0000 UTC", "+0000"))
        end = ciso8601.parse_datetime(row.get("report_period_end").replace(" +0000 UTC", "+0000"))

        key = (cluster_id, start, self._provider_uuid)
        if key in self.processed_report.report_periods:
            return self.processed_report.report_periods[key]

        if key in self.existing_report_periods_map:
            return self.existing_report_periods_map[key]

        data = {
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
            "report_period_start": start,
            "report_period_end": end,
            "provider_id": self._provider_uuid,
        }

        with transaction.atomic():
            report_period_id = report_db_accessor.insert_on_conflict_do_nothing(
                table_name, data, conflict_columns=["cluster_id", "report_period_start", "provider_id"]
            )

        self.processed_report.report_periods[key] = report_period_id

        return report_period_id

    def _process_openshift_labels(self, label_string):
        """Convert the report string to a JSON dictionary.

        Args:
            label_string (str): The raw report string of pod labels

        Returns:
            (str): The JSON dictionary as a string made from the label string

        """
        label_dict = utils.process_openshift_labels(label_string)
        return json.dumps(label_dict)

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_report_periods_map.update(self.processed_report.report_periods)
        self.existing_report_map.update(self.processed_report.reports)

        self.processed_report.remove_processed_rows()

    def process(self):
        """Process usage report file.

        Returns:
            (None)

        """
        row_count = 0
        opener, mode = self._get_file_opener(self._compression)
        with opener(self._report_path, mode) as f:
            with OCPReportDBAccessor(self._schema) as report_db:
                temp_table = report_db.create_temp_table(self.table_name._meta.db_table, drop_column="id")
                LOG.info(f"File '{self._report_path}' opened for processing")
                reader = csv.DictReader(f)
                for row in reader:
                    li_usage_dt = row.get("report_period_start")
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

                    report_period_id = self._create_report_period(
                        row, self._cluster_id, report_db, self._cluster_alias
                    )
                    report_id = self._create_report(row, report_period_id, report_db)

                    self._create_usage_report_line_item(row, report_period_id, report_id, report_db)
                    if len(self.processed_report.line_items) >= self._batch_size:
                        LOG.info(
                            "Saving report rows %d to %d for %s",
                            row_count,
                            row_count + len(self.processed_report.line_items),
                            self._report_name,
                        )
                        self._save_to_db(temp_table, report_db)
                        report_db.merge_temp_table(
                            self.table_name._meta.db_table,
                            temp_table,
                            self.line_item_columns,
                            self.line_item_conflict_columns,
                        )
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
                    report_db.merge_temp_table(
                        self.table_name._meta.db_table,
                        temp_table,
                        self.line_item_columns,
                        self.line_item_conflict_columns,
                    )
                    row_count += len(self.processed_report.line_items)

        LOG.info("Completed report processing for file: %s and schema: %s", self._report_path, self._schema)

        if not settings.DEVELOPMENT:
            LOG.info("Removing processed file: %s", self._report_path)
            remove(self._report_path)

    def _save_to_db(self, temp_table, report_db):
        # Create any needed partitions
        existing_partitions = report_db.get_existing_partitions(OCPUsageLineItemDailySummary)
        report_db.add_partitions(existing_partitions, self.processed_report.requested_partitions)
        # Save batch to DB
        super()._save_to_db(temp_table, report_db)


class OCPCpuMemReportProcessor(OCPReportProcessorBase):
    """OCP Usage Report processor."""

    report_type = "OCPCpuMemReport"

    def __init__(self, schema_name, report_path, compression, provider_uuid):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(
            schema_name=schema_name, report_path=report_path, compression=compression, provider_uuid=provider_uuid
        )
        self.table_name = OCPUsageLineItem()
        stmt = (
            f"Initialized report processor for:\n"
            f" schema_name: {self._schema}\n"
            f" provider_uuid: {provider_uuid}\n"
            f" report_type: {self.report_type}\n"
            f" file: {self._report_path}"
        )
        LOG.info(stmt)

    def _create_usage_report_line_item(self, row, report_period_id, report_id, report_db_accessor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): A report period object id
            report_id (str): A report object id

        Returns:
            (None)

        """
        data = self._get_data_for_table(row, self.table_name._meta.db_table)

        # Skip invalid rows
        if not all([data.get("namespace"), data.get("pod"), data.get("node")]):
            return

        pod_label_str = ""
        if "pod_labels" in data:
            pod_label_str = data.pop("pod_labels")

        data = report_db_accessor.clean_data(data, self.table_name._meta.db_table)

        data["report_period_id"] = report_period_id
        data["report_id"] = report_id
        data["pod_labels"] = self._process_openshift_labels(pod_label_str)
        # Deduplicate potential repeated rows in data
        key = tuple(data.get(column) for column in self.line_item_conflict_columns)
        if key in self.processed_report.line_item_keys:
            return

        self.processed_report.line_items.append(data)
        self.processed_report.line_item_keys[key] = True

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ["report_id", "namespace", "pod", "node"]


class OCPStorageProcessor(OCPReportProcessorBase):
    """OCP Storage Report processor."""

    report_type = "OCPStorageReport"

    def __init__(self, schema_name, report_path, compression, provider_uuid):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(
            schema_name=schema_name, report_path=report_path, compression=compression, provider_uuid=provider_uuid
        )
        self.table_name = OCPStorageLineItem()
        stmt = (
            f"Initialized report processor for:\n"
            f" schema_name: {self._schema}\n"
            f" provider_uuid: {provider_uuid}\n"
            f" report_type: {self.report_type}\n"
            f" file: {self._report_path}"
        )
        LOG.info(stmt)

    def _create_usage_report_line_item(self, row, report_period_id, report_id, report_db_accessor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): A report period object id
            report_id (str): A report object id

        Returns:
            (None)

        """
        data = self._get_data_for_table(row, self.table_name._meta.db_table)

        # Skip invalid rows
        if not all([data.get("namespace"), data.get("persistentvolume")]):
            return

        persistentvolume_labels_str = ""
        if "persistentvolume_labels" in data:
            persistentvolume_labels_str = data.pop("persistentvolume_labels")

        persistentvolumeclaim_labels_str = ""
        if "persistentvolumeclaim_labels" in data:
            persistentvolumeclaim_labels_str = data.pop("persistentvolumeclaim_labels")

        data = report_db_accessor.clean_data(data, self.table_name._meta.db_table)

        data["report_period_id"] = report_period_id
        data["report_id"] = report_id
        data["persistentvolume_labels"] = self._process_openshift_labels(persistentvolume_labels_str)
        data["persistentvolumeclaim_labels"] = self._process_openshift_labels(persistentvolumeclaim_labels_str)

        # Deduplicate potential repeated rows in data
        key = tuple(data.get(column) for column in self.line_item_conflict_columns)
        if key in self.processed_report.line_item_keys:
            return

        self.processed_report.line_items.append(data)
        self.processed_report.line_item_keys[key] = True

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ["report_id", "namespace", "persistentvolumeclaim"]


class OCPNodeLabelProcessor(OCPReportProcessorBase):
    """OCP Node Label Report processor."""

    report_type = "OCPNodeLabelReport"

    def __init__(self, schema_name, report_path, compression, provider_uuid):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(
            schema_name=schema_name, report_path=report_path, compression=compression, provider_uuid=provider_uuid
        )
        self.table_name = OCPNodeLabelLineItem()
        stmt = (
            f"Initialized report processor for:\n"
            f" schema_name: {self._schema}\n"
            f" provider_uuid: {provider_uuid}\n"
            f" report_type: {self.report_type}\n"
            f" file: {self._report_path}"
        )
        LOG.info(stmt)

    def _create_usage_report_line_item(self, row, report_period_id, report_id, report_db_accessor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): A report period object id
            report_id (str): A report object id

        Returns:
            (None)

        """
        data = self._get_data_for_table(row, self.table_name._meta.db_table)

        node_labels_str = ""
        if "node_labels" in data:
            node_labels_str = data.pop("node_labels")

        data = report_db_accessor.clean_data(data, self.table_name._meta.db_table)

        data["report_period_id"] = report_period_id
        data["report_id"] = report_id
        data["node_labels"] = self._process_openshift_labels(node_labels_str)

        # Deduplicate potential repeated rows in data
        key = tuple(data.get(column) for column in self.line_item_conflict_columns)
        if key in self.processed_report.line_item_keys:
            return

        self.processed_report.line_items.append(data)
        self.processed_report.line_item_keys[key] = True

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ["report_id", "node"]
