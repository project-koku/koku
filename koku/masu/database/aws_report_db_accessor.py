#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import json
import logging
import pkgutil
import uuid

from dateutil.parser import parse
from django.conf import settings
from django.db import connection
from django.db.models import F
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.utils import DateHelper
from koku.database import get_model
from koku.database import SQLScriptAtomicExecutorMixin
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.models import OCP_ON_ALL_PERSPECTIVES
from reporting.models import OCP_ON_AWS_PERSPECTIVES
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.models import OCPAllCostLineItemProjectDailySummaryP
from reporting.models import OCPAWSCostLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntry
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItem
from reporting.provider.aws.models import AWSCostEntryLineItemDaily
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryPricing
from reporting.provider.aws.models import AWSCostEntryProduct
from reporting.provider.aws.models import AWSCostEntryReservation
from reporting.provider.aws.models import PRESTO_LINE_ITEM_DAILY_TABLE
from reporting.provider.aws.models import UI_SUMMARY_TABLES
from reporting.provider.aws.openshift.models import UI_SUMMARY_TABLES as OCPAWS_UI_SUMMARY_TABLES


LOG = logging.getLogger(__name__)


class AWSReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
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
        self._table_map = AWS_CUR_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return AWSCostEntryLineItemDailySummary

    @property
    def ocpall_line_item_daily_summary_table(self):
        return get_model("OCPAllCostLineItemDailySummaryP")

    @property
    def ocpall_line_item_project_daily_summary_table(self):
        return get_model("OCPAllCostLineItemProjectDailySummaryP")

    @property
    def line_item_table(self):
        return AWSCostEntryLineItem

    @property
    def cost_entry_table(self):
        return AWSCostEntry

    @property
    def line_item_daily_table(self):
        return AWSCostEntryLineItemDaily

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
        table_name = self._table_map["ocp_on_aws_daily_summary"]
        base_query = self._get_db_obj_query(table_name)
        summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
        return summary_item_query

    def get_ocp_aws_project_summary_query_for_billid(self, bill_id):
        """Get the OCP-on-AWS report project summary item for a given bill query."""
        table_name = self._table_map["ocp_on_aws_project_daily_summary"]
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
        table_name = self._table_map["line_item_daily"]

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
        table_name = self._table_map["line_item_daily_summary"]
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

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            summary_sql = pkgutil.get_data("masu.database", f"sql/aws/{table_name}.sql")
            summary_sql = summary_sql.decode("utf-8")
            summary_sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": source_uuid,
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
        summary_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_awscostentrylineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        summary_sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "table": PRESTO_LINE_ITEM_DAILY_TABLE,
            "source_uuid": source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "markup": markup_value if markup_value else 0,
            "bill_id": bill_id,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)

        LOG.info(f"Summary SQL: {str(summary_sql)}")
        self._execute_presto_raw_sql_query(self.schema, summary_sql)

    def mark_bill_as_finalized(self, bill_id):
        """Mark a bill in the database as finalized."""
        table_name = AWSCostEntryBill
        with schema_context(self.schema):
            bill = self._get_db_obj_query(table_name).get(id=bill_id)

            if bill.finalized_datetime is None:
                bill.finalized_datetime = self.date_accessor.today_with_timezone("UTC")
                bill.save()

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_awstags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
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
        table_name = self._table_map["ocp_on_aws_daily_summary"]
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

    def populate_ocp_on_aws_ui_summary_tables(self, sql_params, tables=OCPAWS_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            summary_sql = pkgutil.get_data("masu.database", f"sql/aws/openshift/{table_name}.sql")
            summary_sql = summary_sql.decode("utf-8")
            summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, sql_params)
            self._execute_raw_sql_query(table_name, summary_sql, bind_params=list(summary_sql_params))

    def delete_ocp_on_aws_hive_partition_by_day(self, days, aws_source, ocp_source, year, month):
        """Deletes partitions individually for each day in days list."""
        table = self._table_map["ocp_on_aws_project_daily_summary"]
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.table_exists_trino(table):
            LOG.info(
                "Deleting partitions for the following: \n\tSchema: %s "
                "\n\tOCP Source: %s \n\tAWS Source: %s \n\tTable: %s \n\tYear-Month: %s-%s \n\tDays: %s",
                self.schema,
                ocp_source,
                aws_source,
                table,
                year,
                month,
                days,
            )
            for day in days:
                for i in range(retries):
                    try:
                        sql = f"""
                            DELETE FROM hive.{self.schema}.{table}
                                WHERE aws_source = '{aws_source}'
                                AND ocp_source = '{ocp_source}'
                                AND year = '{year}'
                                AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                                AND day = '{day}'"""
                        self._execute_presto_raw_sql_query(self.schema, sql)
                        break
                    except TrinoExternalError as err:
                        if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                            continue
                        else:
                            raise err

    def populate_ocp_on_aws_cost_daily_summary_presto(
        self,
        start_date,
        end_date,
        openshift_provider_uuid,
        aws_provider_uuid,
        report_period_id,
        bill_id,
        markup_value,
        distribution,
    ):
        """Populate the daily cost aggregated summary for OCP on AWS.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        # Default to cpu distribution
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = DateHelper().list_days(start_date, end_date)
        days_str = "','".join([str(day.day) for day in days])
        days_list = [str(day.day) for day in days]
        self.delete_ocp_on_aws_hive_partition_by_day(
            days_list, aws_provider_uuid, openshift_provider_uuid, year, month
        )

        pod_column = "pod_usage_cpu_core_hours"
        cluster_column = "cluster_capacity_cpu_core_hours"
        if distribution == "memory":
            pod_column = "pod_usage_memory_gigabyte_hours"
            cluster_column = "cluster_capacity_memory_gigabyte_hours"

        summary_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocpawscostlineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "year": year,
            "month": month,
            "days": days_str,
            "end_date": end_date,
            "aws_source_uuid": aws_provider_uuid,
            "ocp_source_uuid": openshift_provider_uuid,
            "bill_id": bill_id,
            "report_period_id": report_period_id,
            "markup": markup_value,
            "pod_column": pod_column,
            "cluster_column": cluster_column,
        }
        self._execute_presto_multipart_sql_query(self.schema, summary_sql, bind_params=summary_sql_params)

    def back_populate_ocp_on_aws_daily_summary(self, start_date, end_date, report_period_id):
        """Populate the OCP on AWS and OCP daily summary tables. after populating the project table via trino."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"]

        sql = pkgutil.get_data(
            "masu.database", "sql/reporting_ocpawscostentrylineitem_daily_summary_back_populate.sql"
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        self._execute_raw_sql_query(table_name, sql, bind_params=list(sql_params))

    def populate_ocp_on_aws_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["ocp_on_aws_tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpawstags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_markup_cost(self, provider_uuid, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids and start_date and end_date:
                date_filters = {"usage_start__gte": start_date, "usage_start__lte": end_date}
            else:
                date_filters = {}

            OCPALL_MARKUP = (OCPAllCostLineItemDailySummaryP, *OCP_ON_ALL_PERSPECTIVES)
            for bill_id in bill_ids:
                AWSCostEntryLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id, **date_filters).update(
                    markup_cost=(F("unblended_cost") * markup),
                    markup_cost_blended=(F("blended_cost") * markup),
                    markup_cost_savingsplan=(F("savingsplan_effective_cost") * markup),
                )

                OCPAWSCostLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id, **date_filters).update(
                    markup_cost=(F("unblended_cost") * markup)
                )
                for ocpaws_model in OCP_ON_AWS_PERSPECTIVES:
                    ocpaws_model.objects.filter(source_uuid=provider_uuid, **date_filters).update(
                        markup_cost=(F("unblended_cost") * markup)
                    )

                OCPAllCostLineItemProjectDailySummaryP.objects.filter(
                    source_uuid=provider_uuid, source_type="AWS", **date_filters
                ).update(project_markup_cost=(F("pod_cost") * markup))

                for markup_model in OCPALL_MARKUP:
                    markup_model.objects.filter(source_uuid=provider_uuid, source_type="AWS", **date_filters).update(
                        markup_cost=(F("unblended_cost") * markup)
                    )

    def populate_enabled_tag_keys(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.

        Returns
            (None)
        """
        table_name = self._table_map["enabled_tag_keys"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_awsenabledtagkeys.sql")
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
        table_name = self._table_map["line_item_daily_summary"]
        summary_sql = pkgutil.get_data(
            "masu.database", "sql/reporting_awscostentryline_item_daily_summary_update_enabled_tags.sql"
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

    def get_openshift_on_cloud_matched_tags(self, aws_bill_id, ocp_report_period_id):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpaws_matched_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {"bill_id": aws_bill_id, "report_period_id": ocp_report_period_id, "schema": self.schema}
        sql, bind_params = self.jinja_sql.prepare_query(sql, sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(sql, params=bind_params)
            results = cursor.fetchall()

        return [json.loads(result[0]) for result in results]

    def get_openshift_on_cloud_matched_tags_trino(self, aws_source_uuid, ocp_source_uuid, start_date, end_date):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocpaws_matched_tags.sql")
        sql = sql.decode("utf-8")

        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "aws_source_uuid": aws_source_uuid,
            "ocp_source_uuid": ocp_source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
        }
        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        results = self._execute_presto_raw_sql_query(self.schema, sql, bind_params=sql_params)

        return [json.loads(result[0]) for result in results]
