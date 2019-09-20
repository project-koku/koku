#
# Copyright 2019 Red Hat, Inc.
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
"""Database accessor for Azure report data."""
import logging
import pkgutil
import uuid

from dateutil.parser import parse
from django.db.models import F
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.azure.models import (AzureCostEntryBill,
                                             AzureCostEntryLineItemDailySummary,
                                             AzureCostEntryProductService,
                                             AzureMeter)

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class AzureReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with Azure Report reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns

        """
        super().__init__(schema, column_map)
        self._datetime_format = Config.AZURE_DATETIME_STR_FORMAT
        self.column_map = column_map
        self._schema_name = schema
        self.date_accessor = DateAccessor()

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            columns = ['id', 'billing_period_start', 'provider_id']
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {(bill['billing_period_start'], bill['provider_id']): bill['id']
                    for bill in bills}

    def get_products(self):
        """Make a mapping of product objects."""
        table_name = AzureCostEntryProductService
        with schema_context(self.schema):
            columns = ['id', 'instance_id', 'service_name', 'service_tier']
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {(product['instance_id'], product['service_name'],
                     product['service_tier']): product['id']
                    for product in products}

    def get_meters(self):
        """Make a mapping of meter objects."""
        table_name = AzureMeter
        with schema_context(self.schema):
            columns = ['id', 'meter_id']
            meters = self._get_db_obj_query(table_name, columns=columns).all()

            return {(meter['meter_id']): meter['id']
                    for meter in meters}

    # pylint: disable=invalid-name
    def get_cost_entry_bills_query_by_provider(self, provider_id):
        """Return all cost entry bills for the specified provider."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(provider_id=provider_id)

    def bills_for_provider_id(self, provider_id, start_date=None):
        """Return all cost entry bills for provider_id on date."""
        bills = self.get_cost_entry_bills_query_by_provider(provider_id)
        if start_date:
            bill_date = parse(start_date).replace(day=1)
            bills = bills.filter(billing_period_start=bill_date)
        return bills

    def populate_line_item_daily_summary_table(self, start_date, end_date, bill_ids):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = AZURE_REPORT_TABLE_MAP['line_item_daily_summary']
        summary_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_azurecostentrylineitem_daily_summary.sql'
        )
        summary_sql = summary_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date, cost_entry_bill_ids=','.join(bill_ids),
            schema=self.schema
        )
        self._commit_and_vacuum(table_name, summary_sql, start_date, end_date)

    # pylint: disable=invalid-name
    def populate_tags_summary_table(self):
        """Populate the line item aggregated totals data table."""
        table_name = AZURE_REPORT_TABLE_MAP['tags_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_azuretags_summary.sql'
        )
        agg_sql = agg_sql.decode('utf-8').format(schema=self.schema)
        self._commit_and_vacuum(table_name, agg_sql)

    def get_cost_entry_bills_by_date(self, start_date):
        """Return a cost entry bill for the specified start date."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(billing_period_start=start_date)

    def populate_markup_cost(self, markup, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids:
                for bill_id in bill_ids:
                    AzureCostEntryLineItemDailySummary.objects.\
                        filter(cost_entry_bill_id=bill_id).\
                        update(markup_cost=(F('pretax_cost') * markup))
            else:
                AzureCostEntryLineItemDailySummary.objects.\
                    update(markup_cost=(F('pretax_cost') * markup))
