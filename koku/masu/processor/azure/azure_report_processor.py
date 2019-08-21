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
import gzip
import io
import logging
from datetime import datetime

import pytz
from dateutil import parser

from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external import GZIP_COMPRESSED
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util.azure import common as utils
from reporting.provider.azure.models import (AzureCostEntryBill,
                                             AzureCostEntryLineItemDaily,
                                             AzureCostEntryProduct,
                                             AzureMeter,
                                             AzureService)
LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ProcessedAzureReport:
    """Cost usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.bills = {}
        self.products = {}
        self.meters = {}
        self.services = {}
        self.line_items = []

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.bills = {}
        self.products = {}
        self.meters = {}
        self.services = {}
        self.line_items = []


# pylint: disable=too-many-instance-attributes
class AzureReportProcessor(ReportProcessorBase):
    """Cost Usage Report processor."""

    # pylint:disable=too-many-arguments
    def __init__(self, schema_name, report_path, compression, provider_id, manifest_id=None):
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

        self.manifest_id = manifest_id
        self._report_name = report_path
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        self._schema_name = schema_name

        self.processed_report = ProcessedAzureReport()

        # Gather database accessors
        with ReportingCommonDBAccessor() as report_common_db:
            self.column_map = report_common_db.column_map

        with AzureReportDBAccessor(self._schema_name, self.column_map) as report_db:
            self.report_schema = report_db.report_schema
            self.existing_bill_map = report_db.get_cost_entry_bills()
            self.existing_product_map = report_db.get_products()
            self.existing_meter_map = report_db.get_meters()
            self.existing_service_nap = report_db.get_services()

        self.line_item_columns = None

        LOG.info('Initialized report processor for file: %s and schema: %s',
                 report_path, self._schema_name)

    def _get_data_for_table(self, row, table_name):
        """Extract the data from a row for a specific table.

        Args:
            row (dict): A dictionary representation of a CSV file row
            table_name (str): The DB table fields are required for

        Returns:
            (dict): The data from the row keyed on the DB table's column names

        """
        column_map = self.column_map[table_name]

        return {column_map[key]: value
                for key, value in row.items()
                if key in column_map}

    def _create_cost_entry_bill(self, row, report_db_accessor):
        """Create a cost entry bill object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A cost entry bill object id

        """
        table_name = AzureCostEntryBill
        row_date = row.get('UsageDateTime')

        report_date_range = utils.month_date_range(parser.parse(row_date))
        start_date, end_date = report_date_range.split('-')
        subscription_guid = row.get('SubscriptionGuid')

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        key = (subscription_guid, start_date_utc, self._provider_id)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)

        data['provider_id'] = self._provider_id
        data['billing_period_start'] = datetime.strftime(start_date_utc, '%Y-%m-%d %H:%M%z')
        data['billing_period_end'] = datetime.strftime(end_date_utc, '%Y-%m-%d %H:%M%z')

        bill_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['subscription_guid', 'billing_period_start',
                              'provider_id']
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
        table_name = AzureCostEntryProduct
        instance_id = row.get('InstanceId')

        key = (instance_id,)

        if key in self.processed_report.products:
            return self.processed_report.products[key]

        if key in self.existing_product_map:
            return self.existing_product_map[key]

        data = self._get_data_for_table(
            row,
            table_name._meta.db_table
        )
        value_set = set(data.values())
        if value_set == {''}:
            return
        product_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data
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
        meter_id = row.get('MeterId')

        key = (meter_id,)

        if key in self.processed_report.meters:
            return self.processed_report.meters[key]

        if key in self.existing_meter_map:
            return self.existing_meter_map[key]

        data = self._get_data_for_table(
            row,
            table_name._meta.db_table
        )
        value_set = set(data.values())
        if value_set == {''}:
            return
        meter_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data
        )
        self.processed_report.meters[key] = meter_id
        return meter_id

    def _create_service(self, row, report_db_accessor):
        """Create a cost entry product object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the product object

        """
        table_name = AzureService
        service_tier = row.get('ServiceTier')
        service_name = row.get('ServiceName')
        key = (service_tier, service_name)

        if key in self.processed_report.services:
            return self.processed_report.services[key]

        if key in self.existing_service_nap:
            return self.existing_service_nap[key]

        data = self._get_data_for_table(
            row,
            table_name._meta.db_table
        )
        value_set = set(data.values())
        if value_set == {''}:
            return
        service_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['service_tier', 'service_name']
        )
        self.processed_report.services[key] = service_id
        return service_id

    def _process_tags(self, tags_string):
        """Convert the report string to a JSON dictionary.

        Args:
            label_string (str): The raw report string of pod labels

        Returns:
            (dict): The JSON dictionary made from the label string

        """
        return tags_string

    # pylint: disable=too-many-arguments
    def _create_cost_entry_line_item(self,
                                     row,
                                     bill_id,
                                     product_id,
                                     meter_id,
                                     service_id,
                                     report_db_accesor):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            bill_id (str): A processed cost entry bill object id
            product_id (str): A processed product object id
            meter_id (str): A processed meter object id
            service_id (str): A processed object object id

        Returns:
            (None)

        """
        table_name = AzureCostEntryLineItemDaily
        data = self._get_data_for_table(row, table_name._meta.db_table)
        tag_str = ''

        if 'tags' in data:
            tag_str = data.pop('tags')

        data = report_db_accesor.clean_data(
            data,
            table_name._meta.db_table
        )

        data['tags'] = self._process_tags(tag_str)
        data['cost_entry_bill_id'] = bill_id
        data['cost_entry_product_id'] = product_id
        data['meter_id'] = meter_id
        data['service_id'] = service_id

        self.processed_report.line_items.append(data)

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    def create_cost_entry_objects(self, row, report_db_accesor):
        """Create the set of objects required for a row of data."""
        bill_id = self._create_cost_entry_bill(row, report_db_accesor)
        product_id = self._create_cost_entry_product(row, report_db_accesor)
        meter_id = self._create_meter(row, report_db_accesor)
        service_id = self._create_service(row, report_db_accesor)

        self._create_cost_entry_line_item(
            row,
            bill_id,
            product_id,
            meter_id,
            service_id,
            report_db_accesor
        )

        return bill_id

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

    def process(self):
        """Process cost/usage file.

        Returns:
            (None)

        """
        row_count = 0
        # pylint: disable=invalid-name
        opener, mode = self._get_file_opener(self._compression)
        with opener(self._report_path, mode, encoding='utf-8-sig') as f:
            with AzureReportDBAccessor(self._schema_name, self.column_map) as report_db:
                LOG.info('File %s opened for processing', str(f))
                reader = csv.DictReader(f)
                for row in reader:
                    _ = self.create_cost_entry_objects(row, report_db)
                if len(self.processed_report.line_items) >= self._batch_size:
                    LOG.debug('Saving report rows %d to %d for %s', row_count,
                              row_count + len(self.processed_report.line_items),
                              self._report_name)
                    self._save_to_db(report_db)

                    row_count += len(self.processed_report.line_items)
                    self._update_mappings()

                if self.processed_report.line_items:
                    LOG.debug('Saving report rows %d to %d for %s', row_count,
                              row_count + len(self.processed_report.line_items),
                              self._report_name)
                    self._save_to_db(report_db)
                    row_count += len(self.processed_report.line_items)

                report_db.vacuum_table(AZURE_REPORT_TABLE_MAP['line_item'])
                report_db.commit()
                LOG.info('Completed report processing for file: %s and schema: %s',
                         self._report_name, self._schema_name)
            return True

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_product_map.update(self.processed_report.products)
        self.existing_meter_map.update(self.processed_report.meters)
        self.existing_service_nap.update(self.processed_report.services)

        self.processed_report.remove_processed_rows()

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

    def _save_to_db(self, report_db_accessor):
        """Save current batch of records to the database."""
        columns = tuple(self.processed_report.line_items[0].keys())
        csv_file = self._write_processed_rows_to_csv()

        # This will commit all pricing, products, and reservations
        # on the session
        report_db_accessor.commit()
        # This will add line items to the line item table
        report_db_accessor.bulk_insert_rows(
            csv_file,
            AZURE_REPORT_TABLE_MAP['line_item'],
            columns
        )

    # pylint: disable=no-self-use
    def remove_temp_cur_files(self, report_path):
        """Remove temporary report files."""
        pass
