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

"""Helper class for database test classes."""
import csv
import datetime
import io
import random
from decimal import Decimal

from faker import Faker

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP

# A subset of AWS product family values
AWS_PRODUCT_FAMILY = ['Storage', 'Compute Instance',
                      'Database Storage', 'Database Instance']

class ReportObjectCreator:
    """Populate report tables with data for testing."""
    fake = Faker()

    def __init__(self, db_accessor, column_map, column_types):
        """Initialize the report object creation helpler."""
        self.db_accessor = db_accessor
        self.column_map = column_map
        self.column_types = column_types

    def create_cost_entry(self, bill):
        """Create a cost entry database object for test."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        row = self.db_accessor.create_db_object(table_name, {})
        start_datetime = self.fake.past_datetime(start_date='-60d')
        end_datetime = start_datetime + datetime.timedelta(hours=1)
        row.interval_start = self.stringify_datetime(start_datetime)
        row.interval_end = self.stringify_datetime(end_datetime)
        row.bill_id = bill.id

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_cost_entry_bill(self):
        """Create a cost entry bill database object for test."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        data = self.create_columns_for_table(table_name)
        row = self.db_accessor.create_db_object(table_name, data)

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row


    def create_cost_entry_pricing(self):
        """Create a cost entry pricing database object for test."""
        table_name = AWS_CUR_TABLE_MAP['pricing']
        data = self.create_columns_for_table(table_name)
        row = self.db_accessor.create_db_object(table_name, data)

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_cost_entry_product(self):
        """Create a cost entry product database object for test."""
        table_name = AWS_CUR_TABLE_MAP['product']
        data = self.create_columns_for_table(table_name)
        row = self.db_accessor.create_db_object(table_name, data)
        row.product_family = random.choice(AWS_PRODUCT_FAMILY)
        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_cost_entry_reservation(self):
        """Create a cost entry reservation database object for test."""
        table_name = AWS_CUR_TABLE_MAP['reservation']
        data = self.create_columns_for_table(table_name)
        row = self.db_accessor.create_db_object(table_name, data)

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_cost_entry_line_item(self,
                                    bill,
                                    cost_entry,
                                    product,
                                    pricing,
                                    reservation):
        """Create a cost entry line item database object for test."""
        table_name = AWS_CUR_TABLE_MAP['line_item']
        data = self.create_columns_for_table(table_name)

        row = self.db_accessor.create_db_object(table_name, data)
        row.cost_entry_bill_id = bill.id
        row.cost_entry_id = cost_entry.id
        row.cost_entry_product_id = product.id
        row.cost_entry_pricing_id = pricing.id
        row.cost_entry_reservation_id = reservation.id
        row.usage_start = cost_entry.interval_start
        row.usage_end = cost_entry.interval_end

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_columns_for_table(self, table):
        """Generate data for a table."""
        data = {}
        columns = self.column_map[table].values()
        column_types = self.column_types[table]

        for column in columns:
            col_type = column_types[column]
            if col_type == int:
                data[column] = self.fake.pyint()
            elif col_type == float:
                data[column] = self.fake.pyfloat()
            elif col_type == datetime.datetime:
                data[column] = self.stringify_datetime(
                    self.fake.past_datetime()
                )
            elif col_type == Decimal:
                data[column] = self.fake.pydecimal(0,7)
            else:
                data[column] = self.fake.pystr()[:8]

        return data

    def create_csv_file_stream(self, row):
        """Create a CSV file object for bulk upload testing."""
        file_obj = io.StringIO()
        writer = csv.writer(
            file_obj,
            delimiter='\t',
            quoting=csv.QUOTE_NONE,
            quotechar=''
        )
        writer.writerow(row)
        file_obj.seek(0)

        return file_obj

    def stringify_datetime(self, dt):
        """Convert datetime to string with AWS formatting."""
        return dt.strftime(Config.AWS_DATETIME_STR_FORMAT)

    def datetimeify_string(self, value):
        """Convert datetime string to datetime with AWS formatting."""
        return datetime.datetime.strptime(value, Config.AWS_DATETIME_STR_FORMAT)
