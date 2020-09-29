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
from datetime import datetime

from dateutil.parser import parse
from django.db.models import F
from django_tenants.utils import schema_context
from jinjasql import JinjaSql

from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDaily
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureCostEntryProductService
from reporting.provider.azure.models import AzureMeter

LOG = logging.getLogger(__name__)


class AzureReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with Azure Report reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._datetime_format = Config.AZURE_DATETIME_STR_FORMAT
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            columns = ["id", "billing_period_start", "provider_id"]
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {(bill["billing_period_start"], bill["provider_id"]): bill["id"] for bill in bills}

    def get_products(self):
        """Make a mapping of product objects."""
        table_name = AzureCostEntryProductService
        with schema_context(self.schema):
            columns = ["id", "instance_id", "instance_type", "service_name", "service_tier"]
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {
                (
                    product["instance_id"],
                    product["instance_type"],
                    product["service_tier"],
                    product["service_name"],
                ): product["id"]
                for product in products
            }

    def get_meters(self):
        """Make a mapping of meter objects."""
        table_name = AzureMeter
        with schema_context(self.schema):
            columns = ["id", "meter_id"]
            meters = self._get_db_obj_query(table_name, columns=columns).all()

            return {(meter["meter_id"]): meter["id"] for meter in meters}

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(provider_id=provider_uuid)

    def bills_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return all cost entry bills for provider_uuid on date."""
        bills = self.get_cost_entry_bills_query_by_provider(provider_uuid)
        if start_date:
            if isinstance(start_date, str):
                start_date = parse(start_date)
            bill_date = start_date.replace(day=1)
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

        _start_date = start_date.date() if isinstance(start_date, datetime) else start_date
        _end_date = end_date.date() if isinstance(end_date, datetime) else end_date

        table_name = AZURE_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_azurecostentrylineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": _start_date,
            "end_date": _end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_tags_summary_table(self, bill_ids):
        """Populate the line item aggregated totals data table."""
        table_name = AZURE_REPORT_TABLE_MAP["tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_azuretags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def get_cost_entry_bills_by_date(self, start_date):
        """Return a cost entry bill for the specified start date."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(billing_period_start=start_date)

    def populate_markup_cost(self, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids and start_date and end_date:
                for bill_id in bill_ids:
                    AzureCostEntryLineItemDailySummary.objects.filter(
                        cost_entry_bill_id=bill_id, usage_start__gte=start_date, usage_start__lte=end_date
                    ).update(markup_cost=(F("pretax_cost") * markup))
            elif bill_ids:
                for bill_id in bill_ids:
                    AzureCostEntryLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id).update(
                        markup_cost=(F("pretax_cost") * markup)
                    )

    def get_bill_query_before_date(self, date, provider_uuid=None):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date, provider_id=provider_uuid)
            else:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date)
            return cost_entry_bill_query

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the Azure cost entry line item for a given bill query."""
        table_name = AzureCostEntryLineItemDaily
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return line_item_query

    def get_summary_query_for_billid(self, bill_id):
        """Get the Azure cost summary item for a given bill query."""
        table_name = AzureCostEntryLineItemDailySummary
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return summary_item_query

    def populate_ocp_on_azure_cost_daily_summary(self, start_date, end_date, cluster_id, bill_ids, markup_value):
        """Populate the daily cost aggregated summary for OCP on AWS.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazurecostlineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "cluster_id": cluster_id,
            "schema": self.schema,
            "markup": markup_value,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)

        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_ocp_on_azure_tags_summary_table(self):
        """Populate the line item aggregated totals data table."""
        table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazuretags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))
