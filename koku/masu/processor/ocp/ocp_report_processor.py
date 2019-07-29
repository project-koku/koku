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

# pylint: skip-file
# Disabling for now since there are overlaps with AWSReportProcessor.
# Addressing all lint errors would impact both report processors.

import csv
import gzip
import io
import json
import logging
from datetime import datetime
from enum import Enum
from os import listdir, path, remove

from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external import GZIP_COMPRESSED
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util.common import extract_uuids_from_string

from reporting.provider.ocp.models import OCPUsageReportPeriod, OCPUsageReport, OCPUsageLineItem, OCPStorageLineItem

LOG = logging.getLogger(__name__)


class OCPReportProcessorError(Exception):
    """OCPReportProcessor Error."""


class OCPReportTypes(Enum):
    """Types of OCP report files."""

    CPU_MEM_USAGE = 1
    STORAGE = 2
    UNKNOWN = 3


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


class OCPReportProcessor():
    """OCP Usage Report processor."""

    storage_columns = ['report_period_start', 'report_period_end', 'interval_start',
                       'interval_end', 'namespace', 'pod', 'persistentvolumeclaim',
                       'persistentvolume', 'storageclass', 'persistentvolumeclaim_capacity_bytes',
                       'persistentvolumeclaim_capacity_byte_seconds',
                       'volume_request_storage_byte_seconds',
                       'persistentvolumeclaim_usage_byte_seconds', 'persistentvolume_labels',
                       'persistentvolumeclaim_labels']

    cpu_mem_usage_columns = ['report_period_start', 'report_period_end', 'pod', 'namespace',
                             'node', 'resource_id', 'interval_start', 'interval_end',
                             'pod_usage_cpu_core_seconds', 'pod_request_cpu_core_seconds',
                             'pod_limit_cpu_core_seconds', 'pod_usage_memory_byte_seconds',
                             'pod_request_memory_byte_seconds', 'pod_limit_memory_byte_seconds',
                             'node_capacity_cpu_cores', 'node_capacity_cpu_core_seconds',
                             'node_capacity_memory_bytes', 'node_capacity_memory_byte_seconds',
                             'pod_labels']

    def __init__(self, schema_name, report_path, compression, provider_id):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        self._processor = None
        self.report_type = self._detect_report_type(report_path)
        print('FOUND REPORT TYPE: ', str(self.report_type))
        if self.report_type == OCPReportTypes.CPU_MEM_USAGE:
            import pdb; pdb.set_trace()
            self._processor = OCPCpuMemReportProcessor(schema_name, report_path,
                                                       compression, provider_id)
        elif self.report_type == OCPReportTypes.STORAGE:
            self._processor = OCPStorageProcessor(schema_name, report_path,
                                                  compression, provider_id)
        elif self.report_type == OCPReportTypes.UNKNOWN:
            raise OCPReportProcessorError('Unknown OCP report type.')
        print('_PROCESSOR: ', str(self._processor))

    def _detect_report_type(self, report_path):
        """Detect OCP report type."""
        report_type = OCPReportTypes.UNKNOWN
        with open(report_path) as report_file:
            reader = csv.reader(report_file)
            column_names = next(reader)
            if sorted(column_names) == sorted(self.storage_columns):
                report_type = OCPReportTypes.STORAGE
                print('FOUND STORAGE TYPE')
            elif sorted(column_names) == sorted(self.cpu_mem_usage_columns):
                print('FOUND CPU_MEM USAGE TYPE')
                report_type = OCPReportTypes.CPU_MEM_USAGE
        return report_type

    def process(self):
        """Process report file."""
        return self._processor.process()

    def remove_temp_cur_files(self, report_path, manifest_id):
        """Remove temporary report files."""
        files = listdir(report_path)

        print('Cleaning up temporary report files for %s', report_path)
        victim_list = []
        current_assembly_id = None
        for file in files:
            file_path = '{}/{}'.format(report_path, file)
            if file.endswith('manifest.json'):
                with open(file_path, 'r') as manifest_file_handle:
                    manifest_json = json.load(manifest_file_handle)
                    current_assembly_id = manifest_json.get('uuid')
            else:
                with ReportStatsDBAccessor(file, manifest_id) as stats:
                    completed_date = stats.get_last_completed_datetime()
                    if completed_date:
                        assembly_id = extract_uuids_from_string(file).pop()

                        victim_list.append({'file': file_path,
                                            'completed_date': completed_date,
                                            'uuid': assembly_id})

        removed_files = []
        for victim in victim_list:
            if victim['uuid'] != current_assembly_id:
                try:
                    print('Removing %s, completed processing on date %s',
                             victim['file'], victim['completed_date'])
                    remove(victim['file'])
                    removed_files.append(victim['file'])
                except FileNotFoundError:
                    print('Unable to locate file: %s', victim['file'])
        return removed_files


class OCPReportProcessorBase(ReportProcessorBase):
    """Base class for OCP report processing."""

    def __init__(self, schema_name, report_path, compression, provider_id):
        """Initialize base class."""
        super().__init__(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider_id=provider_id
        )
        print('OCPREPORTPROCESSORBASE super complete')
        self._report_name = path.basename(report_path)
        self._cluster_id = report_path.split('/')[-2]

        self._datetime_format = Config.OCP_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        print('GETTING REPORTCOMMONDB ACCESSOR')
        with ReportingCommonDBAccessor() as report_common_db:
            self.column_map = report_common_db.column_map

        print('GETTING OCBREPORTDBACCESSOR')
        with OCPReportDBAccessor(self._schema_name, self.column_map) as report_db:
            print('IN OCPREPORTDBACCESSOR')
            self.existing_report_periods_map = report_db.get_report_periods()
            print('GOT EXISTING PERIODS')
            self.existing_report_map = report_db.get_reports()
            print('GOT REPORTS')

        self.line_item_columns = None
        self.processed_report = ProcessedOCPReport()
        print('BASE INITIALIZED')

    def _get_file_opener(self, compression):
        """Get the file opener for the file's compression.

        Args:
            compression (str): The compression format for the file.

        Returns:
            (file opener, str): The proper file stream handler for the
                compression and the read mode for the file

        """
        if compression == GZIP_COMPRESSED:
            return gzip.open, 'rt'
        return open, 'r'    # assume uncompressed by default

    def _get_data_for_table(self, row, table_name):
        """Extract the data from a row for a specific table.

        Args:
            row (dict): A dictionary representation of a CSV file row
            table_name (str): The DB table fields are required for

        Returns:
            (dict): The data from the row keyed on the DB table's column names

        """
        column_map = self.column_map[table_name._meta.db_table]

        return {column_map[key]: value
                for key, value in row.items()
                if key in column_map}

    def _create_report(self, row, report_period_id, report_db_accessor):
        """Create a report object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): report period object id

        Returns:
            (str): The DB id of the report object

        """
        table_name = OCPUsageReport
        start = datetime.strptime(row.get('interval_start'), Config.OCP_DATETIME_STR_FORMAT)
        end = datetime.strptime(row.get('interval_end'), Config.OCP_DATETIME_STR_FORMAT)

        key = (report_period_id, start)
        if key in self.processed_report.reports:
            return self.processed_report.reports[key]

        if key in self.existing_report_map:
            return self.existing_report_map[key]

        data = {
            'report_period_id': report_period_id,
            'interval_start': start,
            'interval_end': end
        }
        report_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['report_period_id', 'interval_start']
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
        start = datetime.strptime(row.get('report_period_start'), Config.OCP_DATETIME_STR_FORMAT)
        end = datetime.strptime(row.get('report_period_end'), Config.OCP_DATETIME_STR_FORMAT)

        key = (cluster_id, start, self._provider_id)
        if key in self.processed_report.report_periods:
            return self.processed_report.report_periods[key]

        if key in self.existing_report_periods_map:
            return self.existing_report_periods_map[key]

        data = {
            'cluster_id': cluster_id,
            'report_period_start': start,
            'report_period_end': end,
            'provider_id': self._provider_id
        }

        report_period_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['cluster_id', 'report_period_start', 'provider_id']
        )

        self.processed_report.report_periods[key] = report_period_id

        return report_period_id

    def _process_pod_labels(self, label_string):
        """Convert the report string to a JSON dictionary.

        Args:
            label_string (str): The raw report string of pod labels

        Returns:
            (dict): The JSON dictionary made from the label string

        """
        labels = label_string.split('|') if label_string else []
        label_dict = {}

        for label in labels:
            try:
                key, value = label.split(':')
                key = key.replace('label_', '')
                label_dict[key] = value
            except ValueError as err:
                print(err)
                print('%s could not be properly split', label)
                continue

        return json.dumps(label_dict)

    def _write_processed_rows_to_csv(self):
        """Output CSV content to file stream object."""
        values = [tuple(item.values())
                  for item in self.processed_report.line_items]

        file_obj = io.StringIO()
        writer = csv.writer(
            file_obj,
            delimiter='\t',
            quoting=csv.QUOTE_NONE,
            quotechar=''
        )
        writer.writerows(values)
        file_obj.seek(0)

        return file_obj

    def _save_to_db(self, temp_table, report_db_accessor):
        """Save current batch of records to the database."""
        columns = tuple(self.processed_report.line_items[0].keys())
        csv_file = self._write_processed_rows_to_csv()

        # This will commit all pricing, products, and reservations
        # on the session
        report_db_accessor.commit()

        report_db_accessor.bulk_insert_rows(
            csv_file,
            temp_table,
            columns)

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
        print('IN OCP process()')
        with opener(self._report_path, mode) as f:
            with OCPReportDBAccessor(self._schema_name, self.column_map) as report_db:
                temp_table = report_db.create_temp_table(
                    self.table_name._meta.db_table,
                    drop_column='id'
                )

                print('File %s opened for processing', str(f))
                reader = csv.DictReader(f)
                print('FILE TO PROCESS')
                for row in reader:
                    print('ROW: ', str(row))
                    print('CREATING REPORT PERIOD')
                    report_period_id = self._create_report_period(row, self._cluster_id, report_db)
                    print('CREATED REPORT PERIOD')
                    report_id = self._create_report(row, report_period_id, report_db)
                    print('CREATED REPORT')

                    self._create_usage_report_line_item(row, report_period_id, report_id, report_db)
                    print('CREATED USAGE LINE ITEM')
                    if len(self.processed_report.line_items) >= self._batch_size:
                        self._save_to_db(temp_table, report_db)

                        report_db.merge_temp_table(
                            self.table_name,
                            temp_table,
                            self.line_item_columns,
                            self.line_item_conflict_columns
                        )

                        print('Saving report rows %d to %d for %s', row_count,
                                 row_count + len(self.processed_report.line_items),
                                 self._report_name)
                        row_count += len(self.processed_report.line_items)

                        self._update_mappings()

                if self.processed_report.line_items:
                    print('SAVING TO DB')
                    self._save_to_db(temp_table, report_db)

                    report_db.merge_temp_table(
                        self.table_name._meta.db_table,
                        temp_table,
                        self.line_item_columns,
                        self.line_item_conflict_columns
                    )

                    print('Saving report rows %d to %d for %s', row_count,
                             row_count + len(self.processed_report.line_items),
                             self._report_name)

                    row_count += len(self.processed_report.line_items)

        print('Completed report processing for file: %s and schema: %s',
                 self._report_path, self._schema_name)


class OCPCpuMemReportProcessor(OCPReportProcessorBase):
    """OCP Usage Report processor."""

    def __init__(self, schema_name, report_path, compression, provider_id):
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
            provider_id=provider_id
        )
        self.table_name = OCPUsageLineItem()
        print('Initialized report processor for file: %s and schema: %s',
                 self._report_path, self._schema_name)

    def _create_usage_report_line_item(self,
                                       row,
                                       report_period_id,
                                       report_id,
                                       report_db_accessor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): A report period object id
            report_id (str): A report object id

        Returns:
            (None)

        """
        data = self._get_data_for_table(row, self.table_name)
        print('USAGE LINE ITEM DATA: ', str(data))
        pod_label_str = ''
        if 'pod_labels' in data:
            pod_label_str = data.pop('pod_labels')

        data = report_db_accessor.clean_data(
            data,
            self.table_name._meta.db_table
        )

        data['report_period_id'] = report_period_id
        data['report_id'] = report_id
        data['pod_labels'] = self._process_pod_labels(pod_label_str)
        print('USAGE LINE ITEM new data set')
        # Deduplicate potential repeated rows in data
        key = tuple(data.get(column)
                    for column in self.line_item_conflict_columns)
        if key in self.processed_report.line_item_keys:
            return

        self.processed_report.line_items.append(data)
        self.processed_report.line_item_keys[key] = True

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ['report_id', 'namespace', 'pod', 'node']


class OCPStorageProcessor(OCPReportProcessorBase):
    """OCP Usage Report processor."""

    def __init__(self, schema_name, report_path, compression, provider_id):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        print('IN STORAGE PROCESSOR')
        super().__init__(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider_id=provider_id
        )
        print('STORAGE PROCESSOR SUPER INITIALDFD')
        self.table_name = OCPStorageLineItem()
        print('Initialized report processor for file: %s and schema: %s',
                 self._report_path, self._schema_name)

    def _create_usage_report_line_item(self,
                                       row,
                                       report_period_id,
                                       report_id,
                                       report_db_accessor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): A report period object id
            report_id (str): A report object id

        Returns:
            (None)

        """
        data = self._get_data_for_table(row, self.table_name)

        persistentvolume_labels_str = ''
        if 'persistentvolume_labels' in data:
            persistentvolume_labels_str = data.pop('persistentvolume_labels')

        persistentvolumeclaim_labels_str = ''
        if 'persistentvolumeclaim_labels' in data:
            persistentvolumeclaim_labels_str = data.pop('persistentvolumeclaim_labels')

        data = report_db_accessor.clean_data(
            data,
            self.table_name._meta.db_table
        )

        data['report_period_id'] = report_period_id
        data['report_id'] = report_id
        data['persistentvolume_labels'] = self._process_pod_labels(persistentvolume_labels_str)
        data['persistentvolumeclaim_labels'] = self._process_pod_labels(persistentvolumeclaim_labels_str)

        # Deduplicate potential repeated rows in data
        key = tuple(data.get(column)
                    for column in self.line_item_conflict_columns)
        if key in self.processed_report.line_item_keys:
            return

        self.processed_report.line_items.append(data)
        self.processed_report.line_item_keys[key] = True

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ['report_id', 'namespace', 'persistentvolumeclaim']
