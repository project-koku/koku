#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Database accessor for report data."""

import logging
import pkgutil
import uuid

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class ReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns
        """
        super().__init__(schema, column_map)
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self.column_map = column_map

    def get_current_cost_entry_bill(self, bill_id=None):
        """Get the most recent cost entry bill object."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        billing_start = getattr(
            getattr(self.report_schema, table_name),
            'billing_period_start'
        )
        if bill_id is not None:
            return self._get_db_obj_query(table_name).filter(id=bill_id).first()

        return self._get_db_obj_query(table_name)\
            .order_by(billing_start.desc())\
            .first()

    def get_bill_query_before_date(self, date):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        billing_start = getattr(
            getattr(self.report_schema, table_name),
            'billing_period_start'
        )
        base_query = self._get_db_obj_query(table_name)
        cost_entry_bill_query = base_query.filter(billing_start <= date)
        return cost_entry_bill_query

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the AWS cost entry line item for a given bill query."""
        table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_bill_id = getattr(
            getattr(self.report_schema, table_name),
            'cost_entry_bill_id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(cost_entry_bill_id == bill_id)
        return line_item_query

    def get_cost_entry_query_for_billid(self, bill_id):
        """Get the AWS cost entry data for a given bill query."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cost_entry_bill_id = getattr(
            getattr(self.report_schema, table_name),
            'bill_id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(cost_entry_bill_id == bill_id)
        return line_item_query

    def get_cost_entries(self):
        """Make a mapping of cost entries by start time."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        interval_start = getattr(
            getattr(self.report_schema, table_name),
            'interval_start'
        )
        cost_entries = self._get_db_obj_query(table_name)\
            .order_by(interval_start.desc())\
            .all()

        return {entry.interval_start.strftime(self._datetime_format): entry.id
                for entry in cost_entries}

    def get_products(self):
        """Make a mapping of product sku to product objects."""
        table_name = AWS_CUR_TABLE_MAP['product']
        columns = ['id', 'sku', 'product_name', 'region']
        products = self._get_db_obj_query(table_name, columns=columns).all()

        return {(product.sku, product.product_name, product.region): product.id
                for product in products}

    def get_pricing(self):
        """Make a mapping of pricing values string to pricing objects."""
        table_name = AWS_CUR_TABLE_MAP['pricing']
        pricing = self._get_db_obj_query(table_name).all()

        return {'{term}-{unit}'.format(term=p.term, unit=p.unit): p.id
                for p in pricing}

    def get_reservations(self):
        """Make a mapping of reservation ARN to reservation objects."""
        table_name = AWS_CUR_TABLE_MAP['reservation']
        columns = ['id', 'reservation_arn']
        reservs = self._get_db_obj_query(table_name, columns=columns).all()

        return {res.reservation_arn: res.id for res in reservs}

    def populate_line_item_daily_table(self, start_date, end_date):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = AWS_CUR_TABLE_MAP['line_item_daily']
        daily_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_awscostentrylineitem_daily.sql'
        )
        daily_sql = daily_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date
        )
        LOG.info(f'Updating %s from %s to %s.',
                 table_name, start_date, end_date)
        self._cursor.execute(daily_sql)
        self._pg2_conn.commit()
        self._vacuum_table(table_name)
        LOG.info('Finished updating %s.', table_name)

    # pylint: disable=invalid-name
    def populate_line_item_daily_summary_table(self, start_date, end_date):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = AWS_CUR_TABLE_MAP['line_item_daily_summary']
        summary_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_awscostentrylineitem_daily_summary.sql'
        )
        summary_sql = summary_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date
        )
        LOG.info(f'Updating %s from %s to %s.',
                 table_name, start_date, end_date)
        self._cursor.execute(summary_sql)
        self._pg2_conn.commit()
        self._vacuum_table(table_name)
        LOG.info('Finished updating %s.', table_name)

    # pylint: disable=invalid-name
    def populate_line_item_aggregate_table(self):
        """Populate the line item aggregated totals data table."""
        table_name = AWS_CUR_TABLE_MAP['line_item_aggregates']
        agg_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_awscostentrylineitem_aggregates.sql'
        )
        agg_sql = agg_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_')
        )
        LOG.info('Updating %s.', table_name)
        self._cursor.execute(agg_sql)
        self._pg2_conn.commit()
        self._vacuum_table(table_name)
        LOG.info(f'Finished updating %s.', table_name)
