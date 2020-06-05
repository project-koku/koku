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

from dateutil.parser import parse
from django.db.models import F
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.aws.models import AWSCostEntry
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItem
from reporting.provider.aws.models import AWSCostEntryLineItemDaily
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryPricing
from reporting.provider.aws.models import AWSCostEntryProduct
from reporting.provider.aws.models import AWSCostEntryReservation

LOG = logging.getLogger(__name__)


class AWSReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = AWSCostEntryBill
        with schema_context(self.schema):
            columns = ["id", "bill_type", "payer_account_id", "billing_period_start", "provider_id"]
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {
                (bill["bill_type"], bill["payer_account_id"], bill["billing_period_start"], bill["provider_id"]): bill[
                    "id"
                ]
                for bill in bills
            }

    def get_cost_entry_bills_by_date(self, start_date):
        """Return a cost entry bill for the specified start date."""
        table_name = AWSCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(billing_period_start=start_date)

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        table_name = AWSCostEntryBill
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

    def get_bill_query_before_date(self, date, provider_uuid=None):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = AWSCostEntryBill
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date, provider_id=provider_uuid)
            else:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date)
            return cost_entry_bill_query

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the AWS cost entry line item for a given bill query."""
        table_name = AWSCostEntryLineItem
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return line_item_query

    def get_daily_query_for_billid(self, bill_id):
        """Get the AWS cost daily item for a given bill query."""
        table_name = AWSCostEntryLineItemDaily
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return daily_item_query

    def get_summary_query_for_billid(self, bill_id):
        """Get the AWS cost summary item for a given bill query."""
        table_name = AWSCostEntryLineItemDailySummary
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return summary_item_query

    def get_ocp_aws_summary_query_for_billid(self, bill_id):
        """Get the OCP-on-AWS report summary item for a given bill query."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"]
        base_query = self._get_db_obj_query(table_name)
        summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
        return summary_item_query

    def get_ocp_aws_project_summary_query_for_billid(self, bill_id):
        """Get the OCP-on-AWS report project summary item for a given bill query."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_project_daily_summary"]
        base_query = self._get_db_obj_query(table_name)
        summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
        return summary_item_query

    def get_cost_entry_query_for_billid(self, bill_id):
        """Get the AWS cost entry data for a given bill query."""
        table_name = AWSCostEntry
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(bill_id=bill_id)
            return line_item_query

    def get_cost_entries(self):
        """Make a mapping of cost entries by start time."""
        table_name = AWSCostEntry
        with schema_context(self.schema):
            cost_entries = self._get_db_obj_query(table_name).all()

            return {(ce.bill_id, ce.interval_start.strftime(self._datetime_format)): ce.id for ce in cost_entries}

    def get_products(self):
        """Make a mapping of product sku to product objects."""
        table_name = AWSCostEntryProduct
        with schema_context(self.schema):
            columns = ["id", "sku", "product_name", "region"]
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {
                (product["sku"], product["product_name"], product["region"]): product["id"] for product in products
            }

    def get_pricing(self):
        """Make a mapping of pricing values string to pricing objects."""
        table_name = AWSCostEntryPricing
        with schema_context(self.schema):
            pricing = self._get_db_obj_query(table_name).all()

            return {f"{p.term}-{p.unit}": p.id for p in pricing}

    def get_reservations(self):
        """Make a mapping of reservation ARN to reservation objects."""
        table_name = AWSCostEntryReservation
        with schema_context(self.schema):
            columns = ["id", "reservation_arn"]
            reservs = self._get_db_obj_query(table_name, columns=columns).all()

            return {res["reservation_arn"]: res["id"] for res in reservs}

    def populate_line_item_daily_table(self, start_date, end_date, bill_ids):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list)

        Returns
            (None)

        """
        table_name = AWS_CUR_TABLE_MAP["line_item_daily"]

        daily_sql = pkgutil.get_data("masu.database", "sql/reporting_awscostentrylineitem_daily.sql")
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

    def populate_line_item_daily_summary_table(self, start_date, end_date, bill_ids):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_awscostentrylineitem_daily_summary.sql")
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

    def mark_bill_as_finalized(self, bill_id):
        """Mark a bill in the database as finalized."""
        table_name = AWSCostEntryBill
        with schema_context(self.schema):
            bill = self._get_db_obj_query(table_name).get(id=bill_id)

            if bill.finalized_datetime is None:
                bill.finalized_datetime = self.date_accessor.today_with_timezone("UTC")
                bill.save()

    def populate_tags_summary_table(self, bill_ids):
        """Populate the line item aggregated totals data table."""
        table_name = AWS_CUR_TABLE_MAP["tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_awstags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_ocp_on_aws_cost_daily_summary(self, start_date, end_date, cluster_id, bill_ids, markup_value):
        """Populate the daily cost aggregated summary for OCP on AWS.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpawscostlineitem_daily_summary.sql")
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

    def populate_ocp_on_aws_tags_summary_table(self):
        """Populate the line item aggregated totals data table."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpawstags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_markup_cost(self, markup, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids:
                for bill_id in bill_ids:
                    AWSCostEntryLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id).update(
                        markup_cost=(F("unblended_cost") * markup)
                    )
            else:
                AWSCostEntryLineItemDailySummary.objects.update(markup_cost=(F("unblended_cost") * markup))
