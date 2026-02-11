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
from django.db import connection
from django.db.models import F
from django.db.models import Q
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from koku.database import get_model
from koku.database import SQLScriptAtomicExecutorMixin
from koku.reportdb_accessor import get_report_db_accessor
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.processor import is_tag_processing_disabled
from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata
from reporting.models import OCP_ON_ALL_PERSPECTIVES
from reporting.models import OCP_ON_AWS_PERSPECTIVES
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.models import OCPAllCostLineItemProjectDailySummaryP
from reporting.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import TRINO_OCP_AWS_DAILY_SUMMARY_TABLE
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

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        return AWSCostEntryBill.objects.filter(provider_id=provider_uuid)

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
        return AWSCostEntryBill.objects.filter(billing_period_start__lte=date)

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/aws/ui_summary/{table_name}.sql")
            sql = sql.decode("utf-8")
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": source_uuid,
            }
            self._prepare_and_execute_raw_sql_query(
                table_name,
                sql,
                sql_params,
                operation="DELETE/INSERT",
            )

    def populate_line_item_daily_summary_table_trino(self, start_date, end_date, source_uuid, bill_id, markup_value):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        sql = pkgutil.get_data(
            "masu.database", f"{self.trino_sql_folder_name}/aws/reporting_awscostentrylineitem_daily_summary.sql"
        )
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
            sql, sql_params=sql_params, log_ref="reporting_awscostentrylineitem_daily_summary.sql"
        )

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        sql = pkgutil.get_data("masu.database", "sql/aws/reporting_awstags_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_category_summary_table(self, bill_ids, start_date, end_date):
        """Populate the category key values table."""
        table_name = self._table_map["category_summary"]
        sql = pkgutil.get_data("masu.database", "sql/aws/reporting_awscategory_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_ocp_on_aws_category_summary_table(self, bill_ids, start_date, end_date):
        """Populate the OCP on AWS category key values table."""
        sql = pkgutil.get_data("masu.database", "sql/aws/openshift/reporting_ocpawscategory_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query("reporting_ocpawscategory_summary", sql, sql_params)

    def populate_ocp_on_aws_ui_summary_tables(self, sql_params, tables=OCPAWS_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/aws/openshift/ui_summary/{table_name}.sql")
            sql = sql.decode("utf-8")
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_ocp_on_aws_ui_summary_tables_trino(
        self, start_date, end_date, openshift_provider_uuid, aws_provider_uuid, tables=OCPAWS_UI_SUMMARY_TABLES
    ):
        """Populate our UI summary tables (formerly materialized views)."""
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        days_tup = tuple(str(day.day) for day in days)

        for table_name in tables:
            sql = pkgutil.get_data(
                "masu.database", f"{self.trino_sql_folder_name}/aws/openshift/ui_summary/{table_name}.sql"
            )
            sql = sql.decode("utf-8")
            sql_params = {
                "schema": self.schema,
                "start_date": start_date,
                "end_date": end_date,
                "year": year,
                "month": month,
                "days": days_tup,
                "aws_source_uuid": aws_provider_uuid,
                "ocp_source_uuid": openshift_provider_uuid,
            }
            self._execute_trino_raw_sql_query(sql, sql_params=sql_params, log_ref=f"{table_name}.sql")

    def delete_ocp_on_aws_hive_partition_by_day(self, days, aws_source, ocp_source, year, month):
        """Deletes partitions individually for each day in days list."""
        if self.schema_exists_trino() and self.table_exists_trino(TRINO_OCP_AWS_DAILY_SUMMARY_TABLE):
            LOG.info(
                log_json(
                    msg="deleting Hive partitions by day",
                    schema=self.schema,
                    ocp_source=ocp_source,
                    aws_source=aws_source,
                    table=TRINO_OCP_AWS_DAILY_SUMMARY_TABLE,
                    year=year,
                    month=month,
                    days=days,
                )
            )
            for day in days:
                sql = get_report_db_accessor().get_delete_by_day_ocp_on_cloud_sql(
                    schema_name=self.schema,
                    table_name=TRINO_OCP_AWS_DAILY_SUMMARY_TABLE,
                    cloud_source=aws_source,
                    ocp_source=ocp_source,
                    year=year,
                    month=month,
                    day=day,
                )
                self._execute_trino_raw_sql_query(
                    sql,
                    context={"year": year, "month": month, "day": day, "table": TRINO_OCP_AWS_DAILY_SUMMARY_TABLE},
                    log_ref="delete_ocp_on_aws_hive_partition_by_day",
                )

    def _get_matched_tags_strings(self, bill_id, aws_provider_uuid, ocp_provider_uuid, start_date, end_date):
        """Returns the matched tags"""
        ctx = {
            "schema": self.schema,
            "bill_id": bill_id,
            "aws_provider_uuid": aws_provider_uuid,
            "ocp_provider_uuid": ocp_provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
        }
        matched_tags = []
        with schema_context(self.schema):
            enabled_tags = self.check_for_matching_enabled_keys()
            if EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).exists() and enabled_tags:
                matched_tags = self.get_openshift_on_cloud_matched_tags(bill_id)
        if not matched_tags and enabled_tags:
            LOG.info(log_json(msg="matched tags not available via Postgres", context=ctx))
            if is_tag_processing_disabled(self.schema):
                LOG.info(log_json(msg="trino tag matching disabled for customer", context=ctx))
                return []
            LOG.info(log_json(msg="getting matching tags from Trino", context=ctx))
            matched_tags = self.get_openshift_on_cloud_matched_tags_trino(
                aws_provider_uuid, [ocp_provider_uuid], start_date, end_date, invoice_month=None
            )
        if matched_tags:
            return [json.dumps(match).replace("{", "").replace("}", "") for match in matched_tags]
        return matched_tags

    def populate_ocp_on_aws_cost_daily_summary_trino(
        self,
        start_date,
        end_date,
        openshift_provider_uuid,
        aws_provider_uuid,
        report_period_id,
        bill_id,
    ):
        """Populate the daily cost aggregated summary for OCP on AWS.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        sql_metadata = SummarySqlMetadata(
            self.schema,
            openshift_provider_uuid,
            aws_provider_uuid,
            start_date,
            end_date,
            self._get_matched_tags_strings(bill_id, aws_provider_uuid, openshift_provider_uuid, start_date, end_date),
            bill_id,
            report_period_id,
        )
        managed_path = f"{self.trino_sql_folder_name}/aws/openshift/populate_daily_summary"
        prepare_sql, prepare_params = sql_metadata.prepare_template(
            f"{managed_path}/0_prepare_daily_summary_tables.sql"
        )
        LOG.info(log_json(msg="Preparing tables for OCP on AWS flow", **prepare_params))
        self._execute_trino_multipart_sql_query(prepare_sql, bind_params=prepare_params)
        self.delete_ocp_on_aws_hive_partition_by_day(
            sql_metadata.days_tup,
            sql_metadata.cloud_provider_uuid,
            sql_metadata.ocp_provider_uuid,
            sql_metadata.year,
            sql_metadata.month,
        )
        # Resource Matching
        resource_matching_sql, resource_matching_params = sql_metadata.prepare_template(
            f"{managed_path}/1_resource_matching_by_cluster.sql",
            {
                "matched_tag_array": self.find_openshift_keys_expected_values(sql_metadata),
            },
        )
        self._execute_trino_multipart_sql_query(resource_matching_sql, bind_params=resource_matching_params)
        # Data Transformations for Daily Summary
        daily_summary_sql, daily_summary_params = sql_metadata.prepare_template(
            f"{managed_path}/2_summarize_data_by_cluster.sql",
            {
                **sql_metadata.build_cost_model_params(),
            },
        )
        LOG.info(log_json(msg="executing data transformations for ocp on aws daily summary", **daily_summary_params))
        self._execute_trino_multipart_sql_query(daily_summary_sql, bind_params=daily_summary_params)
        # Insert into postgresql
        psql_insert, psql_params = sql_metadata.prepare_template(
            f"{managed_path}/3_reporting_ocpawscostlineitem_project_daily_summary_p.sql",
        )
        LOG.info(log_json(msg="running OCP on AWS SQL managed flow", **psql_params))
        self._execute_trino_multipart_sql_query(psql_insert, bind_params=psql_params)

    def back_populate_ocp_infrastructure_costs(self, start_date, end_date, report_period_id):
        """Populate the OCP infra costs in daily summary tables after populating the project table via trino."""
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        sql = pkgutil.get_data(
            "masu.database", "sql/aws/openshift/reporting_ocpaws_ocp_infrastructure_back_populate.sql"
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_ocp_on_aws_tag_information(self, bill_ids, start_date, end_date, report_period_id):
        """Populate the line item aggregated totals data table."""
        sql_params = {
            "schema": self.schema,
            "bill_ids": bill_ids,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        # Tag Summary
        sql = pkgutil.get_data("masu.database", "sql/aws/openshift/reporting_ocpawstags_summary.sql")
        sql = sql.decode("utf-8")
        self._prepare_and_execute_raw_sql_query(self._table_map["ocp_on_aws_tags_summary"], sql, sql_params)
        # Tag Mapping
        with schema_context(self.schema):
            # Early return check to see if they have any tag mappings set.
            if not TagMapping.objects.filter(
                Q(child__provider_type=Provider.PROVIDER_AWS) | Q(child__provider_type=Provider.PROVIDER_OCP)
            ).exists():
                LOG.debug("No tag mappings for AWS.")
                return
        sql = pkgutil.get_data("masu.database", "sql/aws/openshift/ocpaws_tag_mapping_update_daily_summary.sql")
        sql = sql.decode("utf-8")
        self._prepare_and_execute_raw_sql_query(self._table_map["ocp_on_aws_project_daily_summary"], sql, sql_params)

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
                    markup_cost_amortized=(F("calculated_amortized_cost") * markup),
                )

                OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                    cost_entry_bill_id=bill_id, **date_filters
                ).update(
                    markup_cost=(F("unblended_cost") * markup),
                    markup_cost_blended=(F("blended_cost") * markup),
                    markup_cost_savingsplan=(F("savingsplan_effective_cost") * markup),
                    markup_cost_amortized=(F("calculated_amortized_cost") * markup),
                )
                for ocpaws_model in OCP_ON_AWS_PERSPECTIVES:
                    ocpaws_model.objects.filter(source_uuid=provider_uuid, **date_filters).update(
                        markup_cost=(F("unblended_cost") * markup),
                        markup_cost_blended=(F("blended_cost") * markup),
                        markup_cost_savingsplan=(F("savingsplan_effective_cost") * markup),
                        markup_cost_amortized=(F("calculated_amortized_cost") * markup),
                    )

                OCPAllCostLineItemProjectDailySummaryP.objects.filter(
                    source_uuid=provider_uuid, source_type=Provider.PROVIDER_AWS, **date_filters
                ).update(project_markup_cost=(F("unblended_cost") * markup))

                for markup_model in OCPALL_MARKUP:
                    markup_model.objects.filter(
                        source_uuid=provider_uuid, source_type=Provider.PROVIDER_AWS, **date_filters
                    ).update(markup_cost=(F("unblended_cost") * markup))

    def update_line_item_daily_summary_with_tag_mapping(self, start_date, end_date, bill_ids=None, table_name=None):
        """
        Updates the line item daily summary table with tag mapping pieces.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns:
            (None)
        """
        with schema_context(self.schema):
            # Early return check to see if they have any tag mappings set.
            if not TagMapping.objects.filter(child__provider_type=Provider.PROVIDER_AWS).exists():
                LOG.debug("No tag mappings for AWS.")
                return

        table_name = table_name if table_name else self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data("masu.database", "sql/aws/aws_tag_mapping_update_summary_tables.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
            "table": table_name,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def get_openshift_on_cloud_matched_tags(self, aws_bill_id):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "sql/aws/openshift/reporting_ocpaws_matched_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {"bill_id": aws_bill_id, "schema": self.schema}
        sql, bind_params = self.prepare_query(sql, sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(sql, params=bind_params)
            results = cursor.fetchall()

        return [json.loads(result[0]) for result in results]

    def get_openshift_on_cloud_matched_tags_trino(
        self, aws_source_uuid, ocp_source_uuids, start_date, end_date, **kwargs
    ):
        """Return a list of matched tags."""
        sql = pkgutil.get_data(
            "masu.database", f"{self.trino_sql_folder_name}/aws/openshift/reporting_ocpaws_matched_tags.sql"
        )
        sql = sql.decode("utf-8")

        days = self.date_helper.list_days(start_date, end_date)

        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "aws_source_uuid": aws_source_uuid,
            "ocp_source_uuids": ocp_source_uuids,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "days": tuple(str(day.day) for day in days),
        }

        results = self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, log_ref="reporting_ocpaws_matched_tags.sql"
        )

        return [json.loads(result[0]) for result in results]

    def check_for_matching_enabled_keys(self):
        """
        Checks the enabled tag keys for matching keys.
        """
        match_sql = f"""
            SELECT COUNT(*) FROM (SELECT COUNT(provider_type) AS p_count FROM
                {self.schema}.reporting_enabledtagkeys WHERE enabled=True AND provider_type IN ('AWS', 'OCP')
                GROUP BY key) AS c WHERE c.p_count > 1;
        """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(match_sql)
            results = cursor.fetchall()
            if results[0][0] < 1:
                LOG.info(log_json(msg="no matching enabled keys for OCP on AWS", schema=self.schema))
                return False
        return True

    def populate_ec2_compute_summary_table_trino(self, source_uuid, start_date, bill_id, markup_value):
        """
        Populate the monthly aggregated summary table for EC2 compute line items via Trino.

        Args:
            source_uuid (str): The unique identifier for the data source.
            start_date (datetime.date): The date representing the start of the billing period to populate.
            bill_id (int): The billing entry ID associated with the data being populated.
            markup_value (float): The markup value to apply to the costs, if any.

        Returns
            (None)
        """

        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        table_name = self._table_map["ec2_compute_summary"]
        msg = "Populating EC2 summary table"
        context = {
            "provider_uuid": source_uuid,
            "schema": self.schema,
            "start_date": f"{year}-{month}-01",
            "table": table_name,
        }
        LOG.info(log_json(msg=msg, context=context))

        sql = pkgutil.get_data("masu.database", f"{self.trino_sql_folder_name}/aws/{table_name}.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "source_uuid": source_uuid,
            "year": year,
            "month": month,
            "markup": markup_value or 0,
            "bill_id": bill_id,
        }

        self._execute_trino_raw_sql_query(sql, sql_params=sql_params, log_ref=f"{table_name}.sql")
