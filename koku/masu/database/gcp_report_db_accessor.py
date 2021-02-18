#
# Copyright 2020 Red Hat, Inc.
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
"""Database accessor for GCP report data."""
import logging
import pkgutil
import uuid
from os import path

from dateutil.parser import parse
from django.db.models import F
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItem
from reporting.provider.gcp.models import GCPCostEntryLineItemDaily
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPCostEntryProductService
from reporting.provider.gcp.models import GCPProject
from reporting.provider.gcp.models import PRESTO_LINE_ITEM_TABLE
from reporting_common.models import CostUsageReportStatus

LOG = logging.getLogger(__name__)


class GCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with GCP Report reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()

    @property
    def line_item_daily_summary_table(self):
        return GCPCostEntryLineItemDailySummary

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            columns = ["id", "billing_period_start", "provider_id"]
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {(bill["billing_period_start"], bill["provider_id"]): bill["id"] for bill in bills}

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(provider_id=provider_uuid)

    def get_cost_entry_bills_by_date(self, start_date):
        """Return a cost entry bill for the specified start date."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(billing_period_start=start_date)

    def get_products(self):
        """Make a mapping of product sku to product objects."""
        table_name = GCPCostEntryProductService
        with schema_context(self.schema):
            columns = ["service_id", "sku_id", "id"]
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {(product["service_id"], product["sku_id"]): product["id"] for product in products}

    def get_projects(self):
        """Make a mapping of projects to project objects."""
        table_name = GCPProject
        with schema_context(self.schema):
            columns = ["account_id", "project_id", "id"]
            projects = self._get_db_obj_query(table_name, columns=columns).all()

            return {(project["account_id"], project["project_id"]): project["id"] for project in projects}

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the GCP cost entry line item for a given bill query."""
        table_name = GCPCostEntryLineItem
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return line_item_query

    def get_daily_query_for_billid(self, bill_id):
        """Get the GCP cost daily item for a given bill query."""
        table_name = GCPCostEntryLineItemDaily
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return daily_item_query

    def get_summary_query_for_billid(self, bill_id):
        """Get the GCP cost summary item for a given bill query."""
        table_name = GCPCostEntryLineItemDailySummary
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return summary_item_query

    def populate_line_item_daily_table(self, start_date, end_date, bill_ids):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list)

        Returns
            (None)

        """
        table_name = GCP_REPORT_TABLE_MAP["line_item_daily"]

        daily_sql = pkgutil.get_data("masu.database", "sql/reporting_gcpcostentrylineitem_daily.sql")
        daily_sql = daily_sql.decode("utf-8")
        daily_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        daily_sql, daily_sql_params = self.jinja_sql.prepare_query(daily_sql, daily_sql_params)
        self._execute_raw_sql_query(table_name, daily_sql, start_date, end_date, bind_params=list(daily_sql_params))

    def bills_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return all cost entry bills for provider_uuid on date."""
        bills = self.get_cost_entry_bills_query_by_provider(provider_uuid)
        if start_date:
            if isinstance(start_date, str):
                start_date = parse(start_date)
            bill_date = start_date.replace(day=1)
            bills = bills.filter(billing_period_start=bill_date)
        return bills

    def get_bill_query_before_date(self, date, provider_uuid=None):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date, provider_id=provider_uuid)
            else:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date)
            return cost_entry_bill_query

    def populate_line_item_daily_summary_table(self, start_date, end_date, bill_ids):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = GCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_gcpcostentrylineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_line_item_daily_summary_table_presto(self, start_date, end_date, source_uuid, bill_id, markup_value):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        summary_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_gcpcostentrylineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        summary_sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "table": PRESTO_LINE_ITEM_TABLE,
            "source_uuid": source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "markup": markup_value if markup_value else 0,
            "bill_id": bill_id,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)

        LOG.info(f"Summary SQL: {str(summary_sql)}")
        self._execute_presto_raw_sql_query(self.schema, summary_sql)

    def populate_tags_summary_table(self, bill_ids):
        """Populate the line item aggregated totals data table."""
        table_name = GCP_REPORT_TABLE_MAP["tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_gcptags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_markup_cost(self, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids and start_date and end_date:
                for bill_id in bill_ids:
                    GCPCostEntryLineItemDailySummary.objects.filter(
                        cost_entry_bill_id=bill_id, usage_start__gte=start_date, usage_start__lte=end_date
                    ).update(markup_cost=(F("unblended_cost") * markup))
            elif bill_ids:
                for bill_id in bill_ids:
                    GCPCostEntryLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id).update(
                        markup_cost=(F("unblended_cost") * markup)
                    )

    def get_gcp_scan_range_from_report_name(self, manifest_id=None, report_name=""):
        """Given a manifest_id return the scan range for the

        """
        scan_range = {}
        if manifest_id:
            record = CostUsageReportStatus.objects.filter(manifest_id=manifest_id).first()
            if record:
                report_path = record.report_name
                report_name = path.basename(report_path)
            else:
                return scan_range
        report_name = path.splitext(report_name)[0]
        try:
            date_range = report_name.split("_")[-1]
            scan_start, scan_end = date_range.split(":")
            scan_range["start"] = scan_start
            scan_range["end"] = scan_end
        except ValueError:
            pass
        return scan_range

    def populate_enabled_tag_keys(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.

        Returns
            (None)
        """
        table_name = GCP_REPORT_TABLE_MAP["enabled_tag_keys"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_gcpenabledtagkeys.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def update_line_item_daily_summary_with_enabled_tags(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.

        Returns
            (None)
        """
        table_name = GCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_sql = pkgutil.get_data(
            "masu.database", "sql/reporting_gcpcostentryline_item_daily_summary_update_enabled_tags.sql"
        )
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )
