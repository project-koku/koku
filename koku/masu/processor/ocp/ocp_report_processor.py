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
from datetime import datetime
from enum import Enum
from os import path
from os import remove

from django.conf import settings

from masu.config import Config
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util.ocp import common as utils
from reporting.provider.ocp.models import OCPNodeLabelLineItem
from reporting.provider.ocp.models import OCPStorageLineItem
from reporting.provider.ocp.models import OCPUsageLineItem
from reporting.provider.ocp.models import OCPUsageReport
from reporting.provider.ocp.models import OCPUsageReportPeriod

LOG = logging.getLogger(__name__)


class OCPReportProcessorError(Exception):
    """OCPReportProcessor Error."""


class OCPReportTypes(Enum):
    """Types of OCP report files."""

    CPU_MEM_USAGE = 1
    STORAGE = 2
    NODE_LABELS = 3
    UNKNOWN = 4


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

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.report_periods = {}
        self.reports = {}
        self.line_items = []


class OCPReportProcessor:
    """OCP Usage Report processor."""

    storage_columns = [
        "report_period_start",
        "report_period_end",
        "interval_start",
        "interval_end",
        "namespace",
        "pod",
        "persistentvolumeclaim",
        "persistentvolume",
        "storageclass",
        "persistentvolumeclaim_capacity_bytes",
        "persistentvolumeclaim_capacity_byte_seconds",
        "volume_request_storage_byte_seconds",
        "persistentvolumeclaim_usage_byte_seconds",
        "persistentvolume_labels",
        "persistentvolumeclaim_labels",
    ]

    cpu_mem_usage_columns = [
        "report_period_start",
        "report_period_end",
        "pod",
        "namespace",
        "node",
        "resource_id",
        "interval_start",
        "interval_end",
        "pod_usage_cpu_core_seconds",
        "pod_request_cpu_core_seconds",
        "pod_limit_cpu_core_seconds",
        "pod_usage_memory_byte_seconds",
        "pod_request_memory_byte_seconds",
        "pod_limit_memory_byte_seconds",
        "node_capacity_cpu_cores",
        "node_capacity_cpu_core_seconds",
        "node_capacity_memory_bytes",
        "node_capacity_memory_byte_seconds",
        "pod_labels",
    ]

    node_label_columns = [
        "report_period_start",
        "report_period_end",
        "node",
        "interval_start",
        "interval_end",
        "node_labels",
    ]

    def __init__(self, schema_name, report_path, compression, provider_uuid):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        self._processor = None
        self.report_type = self._detect_report_type(report_path)
        if self.report_type == OCPReportTypes.CPU_MEM_USAGE:
            self._processor = OCPCpuMemReportProcessor(schema_name, report_path, compression, provider_uuid)
        elif self.report_type == OCPReportTypes.STORAGE:
            self._processor = OCPStorageProcessor(schema_name, report_path, compression, provider_uuid)
        elif self.report_type == OCPReportTypes.NODE_LABELS:
            self._processor = OCPNodeLabelProcessor(schema_name, report_path, compression, provider_uuid)
        elif self.report_type == OCPReportTypes.UNKNOWN:
            raise OCPReportProcessorError("Unknown OCP report type.")

    def _detect_report_type(self, report_path):
        """Detect OCP report type."""
        report_type = OCPReportTypes.UNKNOWN
        with open(report_path) as report_file:
            reader = csv.reader(report_file)
            column_names = next(reader)
            sorted_columns = sorted(column_names)
            if sorted_columns == sorted(self.storage_columns):
                report_type = OCPReportTypes.STORAGE
            elif sorted_columns == sorted(self.cpu_mem_usage_columns):
                report_type = OCPReportTypes.CPU_MEM_USAGE
            elif sorted_columns == sorted(self.node_label_columns):
                report_type = OCPReportTypes.NODE_LABELS
        return report_type

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
        start = datetime.strptime(row.get("interval_start"), Config.OCP_DATETIME_STR_FORMAT)
        end = datetime.strptime(row.get("interval_end"), Config.OCP_DATETIME_STR_FORMAT)

        key = (report_period_id, start)
        if key in self.processed_report.reports:
            return self.processed_report.reports[key]

        if key in self.existing_report_map:
            return self.existing_report_map[key]

        data = {"report_period_id": report_period_id, "interval_start": start, "interval_end": end}
        report_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name, data, conflict_columns=["report_period_id", "interval_start"]
        )

        self.processed_report.reports[key] = report_id

        return report_id

    def _create_report_period(self, row, cluster_id, report_db_accessor):
        """Create a report period object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            cluster_id (str): cluster ID

        Returns:
            (str): The DB id of the report period object

        """
        table_name = OCPUsageReportPeriod
        start = datetime.strptime(row.get("report_period_start"), Config.OCP_DATETIME_STR_FORMAT)
        end = datetime.strptime(row.get("report_period_end"), Config.OCP_DATETIME_STR_FORMAT)

        key = (cluster_id, start, self._provider_uuid)
        if key in self.processed_report.report_periods:
            return self.processed_report.report_periods[key]

        if key in self.existing_report_periods_map:
            return self.existing_report_periods_map[key]

        data = {
            "cluster_id": cluster_id,
            "report_period_start": start,
            "report_period_end": end,
            "provider_id": self._provider_uuid,
        }

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
            (dict): The JSON dictionary made from the label string

        """
        labels = label_string.split("|") if label_string else []
        label_dict = {}

        for label in labels:
            try:
                key, value = label.split(":")
                key = key.replace("label_", "")
                label_dict[key] = value
            except ValueError as err:
                LOG.warning(err)
                LOG.warning("%s could not be properly split", label)
                continue

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
                LOG.info("File %s opened for processing", str(f))
                reader = csv.DictReader(f)
                for row in reader:
                    report_period_id = self._create_report_period(row, self._cluster_id, report_db)
                    report_id = self._create_report(row, report_period_id, report_db)

                    self._create_usage_report_line_item(row, report_period_id, report_id, report_db)
                    if len(self.processed_report.line_items) >= self._batch_size:
                        self._save_to_db(temp_table, report_db)
                        report_db.merge_temp_table(
                            self.table_name._meta.db_table,
                            temp_table,
                            self.line_item_columns,
                            self.line_item_conflict_columns,
                        )
                        LOG.info(
                            "Saving report rows %d to %d for %s",
                            row_count,
                            row_count + len(self.processed_report.line_items),
                            self._report_name,
                        )
                        row_count += len(self.processed_report.line_items)

                        self._update_mappings()

                if self.processed_report.line_items:
                    self._save_to_db(temp_table, report_db)
                    report_db.merge_temp_table(
                        self.table_name._meta.db_table,
                        temp_table,
                        self.line_item_columns,
                        self.line_item_conflict_columns,
                    )
                    LOG.info(
                        "Saving report rows %d to %d for %s",
                        row_count,
                        row_count + len(self.processed_report.line_items),
                        self._report_name,
                    )

                    row_count += len(self.processed_report.line_items)

        LOG.info("Completed report processing for file: %s and schema: %s", self._report_path, self._schema)

        if not settings.DEVELOPMENT:
            LOG.info("Removing processed file: %s", self._report_path)
            remove(self._report_path)


class OCPCpuMemReportProcessor(OCPReportProcessorBase):
    """OCP Usage Report processor."""

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
