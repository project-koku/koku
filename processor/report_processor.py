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

"""Processor for Cost Usage Reports."""

import csv
import gzip
import io
import json
import logging
from itertools import islice
from os import path

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor import ReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.exceptions import MasuProcessingError
from masu.external import GZIP_COMPRESSED, UNCOMPRESSED
from masu.processor import ALLOWED_COMPRESSIONS

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ProcessedReport:
    """Cost usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.bill_id = None
        self.cost_entries = {}
        self.line_items = []
        self.products = {}
        self.reservations = {}
        self.pricing = {}

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.cost_entries = {}
        self.line_items = []
        self.products = {}
        self.reservations = {}
        self.pricing = {}


# pylint: disable=too-many-instance-attributes
class ReportProcessor:
    """Cost Usage Report processor."""

    def __init__(self, schema_name, report_path, compression, cursor_pos=0):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED
            cursor_pos (int): An integer cursor position in the file.
                The line number to begin processing at.


        """
        if compression.upper() not in ALLOWED_COMPRESSIONS:
            err_msg = f'Compression {compression} is not supported.'
            raise MasuProcessingError(err_msg)

        self._schema_name = schema_name
        self._report_path = report_path
        self._cursor_pos = cursor_pos
        self._compression = compression.upper()
        self._report_name = path.basename(report_path)
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        self.processed_report = ProcessedReport()

        # Gather database accessors
        self.report_common_db = ReportingCommonDBAccessor()
        self.column_map = self.report_common_db.column_map
        self.report_common_db.close_session()

        self.report_db = ReportDBAccessor(schema=self._schema_name,
                                          column_map=self.column_map)
        self.report_schema = self.report_db.report_schema

        self.current_bill = self.report_db.get_current_cost_entry_bill()
        self.existing_cost_entry_map = self.report_db.get_cost_entries()
        self.existing_product_map = self.report_db.get_products()
        self.existing_pricing_map = self.report_db.get_pricing()
        self.existing_reservation_map = self.report_db.get_reservations()

        LOG.info('Initialized report processor for file: %s and schema: %s',
                 self._report_name, self._schema_name)

    def process(self):
        """Process CUR file.

        Returns:
            (int): An updated cursor position.

        """
        row_count = 0
        bill_id = None
        opener, mode = self._get_file_opener(self._compression)

        # pylint: disable=invalid-name
        with opener(self._report_path, mode) as f:
            LOG.info('File %s opened for processing', str(f))
            reader = csv.DictReader(f)
            for row in islice(reader, self._cursor_pos, None):
                if bill_id is None:
                    bill_id = self._create_cost_entry_bill(row)

                cost_entry_id = self._create_cost_entry(row, bill_id)
                product_id = self._create_cost_entry_product(row)
                pricing_id = self._create_cost_entry_pricing(row)
                reservation_id = self._create_cost_entry_reservation(row)

                self._create_cost_entry_line_item(
                    row,
                    cost_entry_id,
                    bill_id,
                    product_id,
                    pricing_id,
                    reservation_id
                )

                if len(self.processed_report.line_items) >= self._batch_size:
                    self._save_to_db()

                    LOG.info('Saving report rows %d to %d', row_count,
                             row_count + len(self.processed_report.line_items))
                    row_count += len(self.processed_report.line_items)

                    self._update_mappings()

            if self.processed_report.line_items:
                self._save_to_db()
                row_count += len(self.processed_report.line_items)
            self.report_db.close_connections()

        LOG.info('Completed report processing for file: %s and schema: %s',
                 self._report_name, self._schema_name)
        return self._cursor_pos + row_count

    # pylint: disable=inconsistent-return-statements, no-self-use
    def _get_file_opener(self, compression):
        """Get the file opener for the file's compression.

        Args:
            compression (str): The compression format for the file.

        Returns:
            (file opener, str): The proper file stream handler for the
                compression and the read mode for the file

        """
        if compression == UNCOMPRESSED:
            return open, 'r'
        elif compression == GZIP_COMPRESSED:
            return gzip.open, 'rt'

    def _save_to_db(self):
        """Save current batch of records to the database."""
        columns = tuple(self.processed_report.line_items[0].keys())
        csv_file = self._write_processed_rows_to_csv()

        # This will commit all pricing, products, and reservations
        # on the session
        self.report_db.commit()

        self.report_db.bulk_insert_rows(
            csv_file,
            AWS_CUR_TABLE_MAP['line_item'],
            columns)

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_cost_entry_map.update(self.processed_report.cost_entries)
        self.existing_product_map.update(self.processed_report.products)
        self.existing_pricing_map.update(self.processed_report.pricing)
        self.existing_reservation_map.update(self.processed_report.reservations)

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

    def _get_data_for_table(self, row, table_name):
        """Extract the data from a row for a specific table.

        Args:
            row (dict): A dictionary representation of a CSV file row
            table_name (str): The DB table fields are required for

        Returns:
            (dict): The data from the row keyed on the DB table's column names

        """
        # Memory can come as a single number or a number with a unit
        # e.g. "1" vs. "1 Gb" so it gets special cased.
        if 'product/memory' in row and row['product/memory'] is not None:
            memory_list = row['product/memory'].split(' ')
            if len(memory_list) > 1:
                memory, unit = row['product/memory'].split(' ')
            else:
                memory = memory_list[0]
                unit = None
            row['product/memory'] = memory
            row['product/memory_unit'] = unit

        column_map = self.column_map[table_name]

        return {column_map[key]: value
                for key, value in row.items()
                if key in column_map}

    # pylint: disable=no-self-use
    def _process_tags(self, row, tag_suffix='resourceTags'):
        """Return a JSON string of AWS resource tags.

        Args:
            row (dict): A dictionary representation of a CSV file row
            tag_suffix (str): A specifier used to identify a value as a tag

        Returns:
            (str): A JSON string of AWS resource tags

        """
        return json.dumps(
            {key: value for key, value in row.items()
             if tag_suffix in key and row[key]}
        )

    # pylint: disable=no-self-use
    def _get_cost_entry_time_interval(self, interval):
        """Split the cost entry time interval into start and end.

        Args:
            interval (str): The time interval from the cost usage report.

        Returns:
            (str, str): Separated start and end strings

        """
        start, end = interval.split('/')
        return start, end

    def _create_cost_entry_bill(self, row):
        """Create a cost entry bill object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): A cost entry bill object id

        """
        table_name = AWS_CUR_TABLE_MAP['bill']
        start_date = row.get('bill/BillingPeriodStartDate')

        current_start = None
        if self.current_bill is not None:
            current_start = self.current_bill.billing_period_start.strftime(
                self._datetime_format
            )

        if current_start is not None and start_date == current_start:
            self.processed_report.bill_id = self.current_bill.id
            return self.current_bill.id

        data = self._get_data_for_table(row, table_name)

        bill_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data
        )
        self.processed_report.bill_id = bill_id

        return bill_id

    def _create_cost_entry(self, row, bill_id):
        """Create a cost entry object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            bill_id (str): The current cost entry bill id

        Returns:
            (str): The DB id of the cost entry object

        """
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        interval = row.get('identity/TimeInterval')
        start, end = self._get_cost_entry_time_interval(interval)

        if start in self.processed_report.cost_entries:
            return self.processed_report.cost_entries[start]
        elif start in self.existing_cost_entry_map:
            return self.existing_cost_entry_map[start]

        data = {
            'bill_id': bill_id,
            'interval_start': start,
            'interval_end': end
        }

        cost_entry_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data
        )
        self.processed_report.cost_entries[start] = cost_entry_id

        return cost_entry_id

    # pylint: disable=too-many-arguments
    def _create_cost_entry_line_item(self,
                                     row,
                                     cost_entry_id,
                                     bill_id,
                                     product_id,
                                     pricing_id,
                                     reservation_id):
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
        table_name = AWS_CUR_TABLE_MAP['line_item']
        data = self._get_data_for_table(row, table_name)
        data = self.report_db.clean_data(
            data,
            table_name
        )

        data['tags'] = self._process_tags(row)
        data['cost_entry_id'] = cost_entry_id
        data['cost_entry_bill_id'] = bill_id
        data['cost_entry_product_id'] = product_id
        data['cost_entry_pricing_id'] = pricing_id
        data['cost_entry_reservation_id'] = reservation_id

        self.processed_report.line_items.append(data)

    def _create_cost_entry_pricing(self, row):
        """Create a cost entry pricing object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the pricing object

        """
        table_name = AWS_CUR_TABLE_MAP['pricing']
        key = '{cost}-{rate}-{term}-{unit}'.format(
            cost=row.get('pricing/publicOnDemandCost'),
            rate=row.get('pricing/publicOnDemandRate'),
            term=row.get('pricing/term'),
            unit=row.get('pricing/unit')
        )

        if key in self.processed_report.pricing:
            return self.processed_report.pricing[key]
        elif key in self.existing_pricing_map:
            return self.existing_pricing_map[key]

        data = self._get_data_for_table(
            row,
            table_name
        )
        value_set = set(data.values())
        if value_set == {''}:
            return

        pricing_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data
        )
        self.processed_report.pricing[key] = pricing_id

        return pricing_id

    def _create_cost_entry_product(self, row):
        """Create a cost entry product object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the product object

        """
        table_name = AWS_CUR_TABLE_MAP['product']
        sku = row.get('product/sku')

        if sku in self.processed_report.products:
            return self.processed_report.products[sku]
        elif sku in self.existing_product_map:
            return self.existing_product_map[sku]

        data = self._get_data_for_table(
            row,
            table_name
        )
        value_set = set(data.values())
        if value_set == {''}:
            return

        product_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data,
            columns=['sku']
        )
        self.processed_report.products[sku] = product_id

        return product_id

    def _create_cost_entry_reservation(self, row):
        """Create a cost entry reservation object.

        Args:
            row (dict): A dictionary representation of a CSV file row

        Returns:
            (str): The DB id of the reservation object

        """
        table_name = AWS_CUR_TABLE_MAP['reservation']
        arn = row.get('reservation/ReservationARN')

        if arn in self.processed_report.reservations:
            return self.processed_report.reservations.get(arn)
        elif arn in self.existing_reservation_map:
            return self.existing_reservation_map[arn]

        data = self._get_data_for_table(
            row,
            table_name
        )
        value_set = set(data.values())
        if value_set == {''}:
            return

        reservation_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data
        )
        self.processed_report.reservations[arn] = reservation_id

        return reservation_id
