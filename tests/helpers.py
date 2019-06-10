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
from math import pow
import uuid
import random
from decimal import Decimal

from dateutil import relativedelta
from faker import Faker

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP, OCP_REPORT_TABLE_MAP
from masu.database.provider_db_accessor import ProviderDBAccessor


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

    def create_cost_entry(self, bill, entry_datetime=None):
        """Create a cost entry database object for test."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        row = self.db_accessor.create_db_object(table_name, {})
        if entry_datetime:
            start_datetime = entry_datetime
        else:
            start_datetime = self.fake.past_datetime(start_date='-60d')
        end_datetime = start_datetime + datetime.timedelta(hours=1)
        row.interval_start = self.stringify_datetime(start_datetime)
        row.interval_end = self.stringify_datetime(end_datetime)
        row.bill_id = bill.id

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_cost_entry_bill(self, bill_date=None, provider_id=None):
        """Create a cost entry bill database object for test."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        data = self.create_columns_for_table(table_name)
        data['provider_id'] = 1
        if provider_id:
            data['provider_id'] = provider_id
        if bill_date:
            bill_start = bill_date.replace(day=1).date()
            bill_end = bill_start + relativedelta.relativedelta(months=1)

            data['billing_period_start'] = bill_start
            data['billing_period_end'] = bill_end

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

    def create_cost_entry_product(self, product_family=None):
        """Create a cost entry product database object for test."""
        table_name = AWS_CUR_TABLE_MAP['product']
        data = self.create_columns_for_table(table_name)
        row = self.db_accessor.create_db_object(table_name, data)
        if product_family:
            row.product_family = product_family
        else:
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
                                    reservation,
                                    resource_id=None):
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
        row.tags = {
            'environment': random.choice(['dev', 'qa', 'prod']),
            self.fake.pystr()[:8]: self.fake.pystr()[:8]
        }
        if resource_id:
            row.resource_id = resource_id
        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_ocp_report_period(self, period_date=None, provider_id=None, cluster_id=None):
        """Create an OCP report database object for test."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        period_start = self.fake.past_datetime().date().replace(day=1)
        period_end = period_start + relativedelta.relativedelta(days=random.randint(1, 15))
        data = {'cluster_id': cluster_id if cluster_id else self.fake.pystr()[:8],
                'provider_id': provider_id if provider_id else 1,
                'report_period_start': self.stringify_datetime(period_start),
                'report_period_end': self.stringify_datetime(period_end)}

        if period_date:
            period_start = period_date.replace(day=1).date()
            period_end = period_start + relativedelta.relativedelta(months=1)

            data['report_period_start'] = period_start
            data['report_period_end'] = period_end

        row = self.db_accessor.create_db_object(table_name, data)

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_ocp_report(self, reporting_period, report_datetime=None):
        """Create an OCP reporting period database object for test."""
        table_name = OCP_REPORT_TABLE_MAP['report']

        data = {'report_period_id': reporting_period.id}
        if report_datetime:
            start_datetime = report_datetime
        else:
            start_datetime = self.fake.past_datetime(start_date='-60d')
        data['interval_start'] = start_datetime
        data['interval_end'] = start_datetime + relativedelta.relativedelta(hours=+1)
        row = self.db_accessor.create_db_object(table_name, data)

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_ocp_usage_line_item(self,
                                   report_period,
                                   report,
                                   resource_id=None):
        """Create an OCP usage line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        data = self.create_columns_for_table(table_name)

        for key in data:
            if 'byte' in key:
                data[key] = data[key] * Decimal(pow(2, 30))

        if resource_id:
            data['resource_id'] = resource_id

        row = self.db_accessor.create_db_object(table_name, data)

        row.report_period_id = report_period.id
        row.report_id = report.id

        self.db_accessor._session.add(row)
        self.db_accessor._session.commit()

        return row

    def create_ocp_storage_line_item(self,
                                   report_period,
                                   report):
        """Create an OCP storage line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item']
        data = self.create_columns_for_table(table_name)

        for key in data:
            if 'bytes' in key or 'byte' in key:
                data[key] = data[key] * Decimal(pow(2, 30)) * 5

        row = self.db_accessor.create_db_object(table_name, data)

        row.report_period_id = report_period.id
        row.report_id = report.id

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
            elif col_type == dict:
                data[column] = {
                    'label_one': self.fake.pystr()[:8],
                    'label_two': self.fake.pystr()[:8]
                }
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

    def create_rate(self, metric, provider_uuid, rates):
        """Create an OCP rate database object for test."""
        table_name = OCP_REPORT_TABLE_MAP['rate']

        data = {'metric': metric,
                'rates': rates,
                'uuid': str(uuid.uuid4())}

        rate_obj = self.db_accessor.create_db_object(table_name, data)

        self.db_accessor._session.add(rate_obj)
        self.db_accessor._session.commit()

        rate_map_table = OCP_REPORT_TABLE_MAP['rate_map']
        provider_obj = ProviderDBAccessor(provider_uuid).get_provider()
        data = {'provider_uuid': provider_obj.uuid, 'rate_id': rate_obj.id}
        rate_map_obj = self.db_accessor.create_db_object(rate_map_table, data)

        self.db_accessor._session.add(rate_map_obj)
        self.db_accessor._session.commit()

        return rate_obj
