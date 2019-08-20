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

from masu.config import Config
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase

from reporting.provider.azure.models import (AzureCostEntryBill,
                                             AzureCostEntryLineItem,
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
        self.cost_entries = {}
        self.line_items = []
        self.products = {}
        self.reservations = {}
        self.pricing = {}

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.bills = {}
        self.cost_entries = {}
        self.line_items = []
        self.products = {}
        self.reservations = {}
        self.pricing = {}


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
            # self.existing_cost_entry_map = report_db.get_cost_entries()
            self.existing_product_map = report_db.get_products()
            # self.existing_pricing_map = report_db.get_pricing()
            # self.existing_reservation_map = report_db.get_reservations()

        LOG.info('Initialized report processor for file: %s and schema: %s',
                 self._report_name, self._schema_name)

    def _create_cost_entry_bill(self, row, report_db_accessor):
        """Create a cost entry bill object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A cost entry bill object id

        """
        table_name = AzureCostEntryBill
        start_date = row.get('UsageDateTime')

        key = (bill_type, payer_account_id, start_date, self._provider_id)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        if key in self.existing_bill_map:
            return self.existing_bill_map[key]

        data = self._get_data_for_table(row, table_name._meta.db_table)

        data['provider_id'] = self._provider_id

        bill_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['bill_type', 'payer_account_id',
                              'billing_period_start', 'provider_id']
        )

        self.processed_report.bills[key] = bill_id

        return bill_id

    # pylint: disable=too-many-arguments
    def _create_cost_entry_line_item(self,
                                     row,
                                     cost_entry_id,
                                     bill_id,
                                     product_id,
                                     pricing_id,
                                     reservation_id,
                                     report_db_accesor):
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
        table_name = AzureCostEntryLineItem
        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = report_db_accesor.clean_data(
            data,
            table_name._meta.db_table
        )

        #data['tags'] = self._process_tags(row)
        #data['cost_entry_id'] = cost_entry_id
        data['cost_entry_bill_id'] = bill_id
        #data['cost_entry_product_id'] = product_id
        #data['cost_entry_pricing_id'] = pricing_id
        #data['cost_entry_reservation_id'] = reservation_id

        self.processed_report.line_items.append(data)

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    def create_cost_entry_objects(self, row, report_db_accesor):
        """Create the set of objects required for a row of data."""
        bill_id = self._create_cost_entry_bill(row, report_db_accesor)
        #cost_entry_id = self._create_cost_entry(row, bill_id, report_db_accesor)
        #product_id = self._create_cost_entry_product(row, report_db_accesor)
        #pricing_id = self._create_cost_entry_pricing(row, report_db_accesor)
        #reservation_id = self._create_cost_entry_reservation(row, report_db_accesor)

        self._create_cost_entry_line_item(
            row,
            None,
            bill_id,
            None,
            None,
            None,
            report_db_accesor
        )

        return bill_id

    def process(self):
        """Process CUR file.

        Returns:
            (None)

        """
        row_count = 0
        # pylint: disable=invalid-name
        with open(self._report_path, 'r') as f:
            with AzureReportDBAccessor(self._schema_name, self.column_map) as report_db:
                LOG.info('File %s opened for processing', str(f))
                reader = csv.DictReader(f)
                for row in reader:
                    bill_id = self.create_cost_entry_objects(row, report_db)

    # pylint: disable=no-self-use
    def remove_temp_cur_files(self, report_path):
        """Remove temporary report files."""
        pass