#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import pkgutil
import uuid

from dateutil.parser import parse
from django.db.models import F
from django_tenants.utils import schema_context

from api.models import Provider
from koku.database import SQLScriptAtomicExecutorMixin
from masu.database import OCI_CUR_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.processor import is_feature_cost_3592_tag_mapping_enabled
from reporting.provider.all.models import TagMapping
from reporting.provider.oci.models import OCICostEntryBill
from reporting.provider.oci.models import OCICostEntryLineItemDailySummary
from reporting.provider.oci.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class OCIReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._table_map = OCI_CUR_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return OCICostEntryLineItemDailySummary

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        return OCICostEntryBill.objects.filter(provider_id=provider_uuid)

    def bills_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return all cost entry bills for provider_uuid on date."""
        bills = self.get_cost_entry_bills_query_by_provider(provider_uuid)
        if start_date:
            if isinstance(start_date, str):
                start_date = parse(start_date)
            bill_date = start_date.replace(day=1)
            bills = bills.filter(billing_period_start=bill_date)
        return bills

    def get_bill_query_before_date(self, date):
        """Get the cost entry bill objects with billing period before provided date."""
        return OCICostEntryBill.objects.filter(billing_period_start__lte=date)

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/oci/{table_name}.sql")
            sql = sql.decode("utf-8")
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": source_uuid,
            }
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")

    def populate_line_item_daily_summary_table_trino(self, start_date, end_date, source_uuid, bill_id, markup_value):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        sql = pkgutil.get_data("masu.database", "trino_sql/reporting_ocicostentrylineitem_daily_summary.sql")
        sql = sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "markup": markup_value or 0,
            "bill_id": bill_id,
        }

        self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, log_ref="reporting_ocicostentrylineitem_daily_summary.sql"
        )

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        sql = pkgutil.get_data("masu.database", "sql/oci/reporting_ocitags_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_markup_cost(self, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            date_filters = {}
            if bill_ids and start_date and end_date:
                date_filters = {"usage_start__gte": start_date, "usage_start__lte": end_date}

            for bill_id in bill_ids:
                OCICostEntryLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id, **date_filters).update(
                    markup_cost=(F("cost") * markup),
                )

    def update_line_item_daily_summary_with_tag_mapping(self, start_date, end_date, bill_ids=None):
        """
        Updates the line item daily summary table with tag mapping pieces.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns:
            (None)
        """
        if not is_feature_cost_3592_tag_mapping_enabled(self.schema):
            return
        with schema_context(self.schema):
            # Early return check to see if they have any tag mappings set.
            if not TagMapping.objects.filter(child__provider_type=Provider.PROVIDER_OCI).exists():
                LOG.debug("No tag mappings for OCI.")
                return

        table_name = self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data("masu.database", "sql/oci/oci_tag_mapping_update_daily_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_enabled_tag_keys(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.

        Returns
            (None)
        """
        table_name = "reporting_enabledtagkeys"
        sql = pkgutil.get_data("masu.database", "sql/oci/reporting_ocienabledtagkeys.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def update_line_item_daily_summary_with_enabled_tags(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.

        Returns
            (None)
        """
        table_name = self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data(
            "masu.database", "sql/oci/reporting_ocicostentryline_item_daily_summary_update_enabled_tags.sql"
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)
