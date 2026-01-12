#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from datetime import datetime

from django.conf import settings
from trino.exceptions import TrinoExternalError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku.reportdb_accessor import get_report_db_accessor
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.common import date_range_pair
from reporting.provider.aws.models import TRINO_LINE_ITEM_DAILY_TABLE as AWS_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.azure.models import TRINO_LINE_ITEM_DAILY_TABLE as AZURE_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import TRINO_LINE_ITEM_DAILY_TABLE as GCP_TRINO_LINE_ITEM_DAILY_TABLE

LOG = logging.getLogger(__name__)

# Filter maps
TRINO_FILTER_MAP = {
    Provider.PROVIDER_AWS: {"date": "lineitem_usagestartdate", "metric": "lineitem_unblendedcost"},
    Provider.PROVIDER_AZURE: {"date": "date", "metric": "costinbillingcurrency"},
    Provider.PROVIDER_GCP: {"date": "usage_start_time", "metric": "cost"},
    Provider.PROVIDER_OCP: {
        "date": "usage_start",
        "metric": "pod_effective_usage_cpu_core_hours",
    },
    "OCPAWS": {"date": "usage_start", "metric": "unblended_cost"},
    "OCPAzure": {"date": "usage_start", "metric": "pretax_cost"},
    "OCPGCP": {"date": "usage_start", "metric": "unblended_cost"},
}
PG_FILTER_MAP = {
    Provider.PROVIDER_AWS: {
        "date": "usage_start",
        "metric": "unblended_cost",
    },
    Provider.PROVIDER_AZURE: {"date": "usage_start", "metric": "pretax_cost"},
    Provider.PROVIDER_GCP: {
        "date": "usage_start",
        "metric": "unblended_cost",
    },
    Provider.PROVIDER_OCP: {
        "date": "usage_start",
        "metric": "pod_effective_usage_cpu_core_hours",
    },
    "OCPAWS": {"date": "usage_start", "metric": "unblended_cost"},
    "OCPAzure": {"date": "usage_start", "metric": "pretax_cost"},
    "OCPGCP": {"date": "usage_start", "metric": "unblended_cost"},
}

# Table maps
PG_TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_CUR_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_AZURE: AZURE_REPORT_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_GCP: GCP_REPORT_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_OCP: OCP_REPORT_TABLE_MAP.get("line_item_daily_summary"),
    "OCPAWS": AWS_CUR_TABLE_MAP.get("ocp_on_aws_project_daily_summary"),
    "OCPAzure": AZURE_REPORT_TABLE_MAP.get("ocp_on_azure_project_daily_summary"),
    "OCPGCP": GCP_REPORT_TABLE_MAP.get("ocp_on_gcp_project_daily_summary"),
}

TRINO_TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_AZURE: AZURE_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_GCP: GCP_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_OCP: "reporting_ocpusagelineitem_daily_summary",
    "OCPAWS": "reporting_ocpawscostlineitem_project_daily_summary",
    "OCPAzure": "reporting_ocpazurecostlineitem_project_daily_summary",
    "OCPGCP": "reporting_ocpgcpcostlineitem_project_daily_summary",
}


class DataValidator:
    """Class to check data is valid for providers"""

    def __init__(
        self,
        schema,
        start_date,
        end_date,
        provider_uuid,
        ocp_on_cloud_type,
        context,
        date_step=settings.TRINO_DATE_STEP,
    ):
        self.dh = DateHelper()
        self.schema = schema
        self.provider_uuid = provider_uuid
        self.ocp_on_cloud_type = ocp_on_cloud_type
        # start_date should include a rolling window
        utc_start = self.dh.set_datetime_utc(start_date)
        self.start_date = (
            self.dh.month_start_utc(utc_start)
            if utc_start.day < 6
            else self.dh.n_days_ago(utc_start, settings.VALIDATION_RANGE)
        )
        # end_date should not cross month boundary
        utc_end = self.dh.set_datetime_utc(end_date)
        self.end_date = self.dh.month_end(utc_start) if utc_start.month != utc_end.month else utc_end
        self.context = context
        self.date_step = date_step

    def get_table_filters_for_provider(self, provider_type, trino=False):
        """Get relevant table and query filters for given provider type"""
        table_map = provider_type
        if self.ocp_on_cloud_type:
            table_map = f"OCP{provider_type}"
        table = PG_TABLE_MAP.get(table_map)
        query_filters = PG_FILTER_MAP.get(table_map)
        if trino:
            table = TRINO_TABLE_MAP.get(table_map)
            query_filters = TRINO_FILTER_MAP.get(table_map)
        return table, query_filters

    def compare_data(self, pg_data, trino_data, tolerance=1):
        """Validate if postgres and trino query data cost matches per day"""
        incomplete_days = {}
        valid_cost = True
        if trino_data == {}:
            # If there is no data in trino then there is nothing to validate against
            return incomplete_days, True
        for date in trino_data:
            if date in pg_data:
                if not abs(pg_data[date] - trino_data[date]) <= tolerance:
                    incomplete_days[date] = {
                        "pg_value": pg_data[date],
                        "trino_value": trino_data[date],
                        "delta": trino_data[date] - pg_data[date],
                    }
                    valid_cost = False
            else:
                incomplete_days[date] = "missing daily data"
                valid_cost = False
        return incomplete_days, valid_cost

    def execute_relevant_query(self, provider_type, cluster_id=None, trino=False):
        """Make relevant postgres or Trino queries"""
        daily_result = {}
        # year and month for running partitioned queries
        year = self.dh.bill_year_from_date(self.start_date)
        month = self.dh.bill_month_from_date(self.start_date)
        report_db_accessor = ReportDBAccessorBase(self.schema)
        # Set provider filter, when running ocp{aws/gcp/azure} checks we need to rely on the cluster id
        provider_filter = self.provider_uuid if not self.ocp_on_cloud_type else cluster_id
        # query trino/postgres
        table, query_filters = self.get_table_filters_for_provider(provider_type, trino)
        for start, end in date_range_pair(self.start_date, self.end_date, step=self.date_step):
            # Determine source column name based on database type and whether it's OCP-on-cloud
            if trino:
                source = "source" if not self.ocp_on_cloud_type else "cluster_id"
            else:
                source = "source_uuid" if not self.ocp_on_cloud_type else "cluster_id"

            sql = get_report_db_accessor().get_data_validation_sql(
                schema_name=self.schema,
                table_name=table,
                source_column=source,
                provider_filter=provider_filter,
                metric=query_filters.get("metric"),
                date_column=query_filters.get("date"),
                start_date=str(start),
                end_date=str(end),
                year=year,
                month=month,
            )

            if trino:
                result = report_db_accessor._execute_trino_raw_sql_query(sql, log_ref="data validation query")
            else:
                result = report_db_accessor._prepare_and_execute_raw_sql_query(
                    table, sql, operation="VALIDATION_QUERY"
                )
            if result != []:
                for day in result:
                    key = day[1].date() if isinstance(day[1], datetime) else day[1]
                    daily_result[key] = float(day[0])
        return daily_result

    def check_data_integrity(self):
        """Helper to call the query and validation methods for validating data"""
        valid_cost = False
        pg_data = None
        trino_data = None
        cluster_id = None
        daily_difference = {}
        self.context["provider_uuid"] = self.provider_uuid

        provider = Provider.objects.filter(uuid=self.provider_uuid).first()
        if provider:
            LOG.info(
                log_json(
                    msg="validation started for provider",
                    start_date=self.start_date,
                    end_date=self.end_date,
                    context=self.context,
                )
            )
            provider_type = provider.type.strip("-local")
            if self.ocp_on_cloud_type:
                provider_type = self.ocp_on_cloud_type.strip("-local")
                cluster_id = provider.authentication.credentials.get("cluster_id")
                self.context["cluster_id"] = cluster_id
            # Postgres query to get daily values
            try:
                pg_data = self.execute_relevant_query(provider_type, cluster_id)
            except Exception as err:
                LOG.warning(log_json(msg="data validation postgres query failed", context=self.context), exc_info=err)
                return
            # Trino query to get daily values
            try:
                trino_data = self.execute_relevant_query(provider_type, cluster_id, True)
            except TrinoExternalError as te:
                # https://github.com/trinodb/trino-python-client/blob/master/trino/client.py
                # The trino external error contains a response
                if "Partition no longer exists" in te.message:
                    LOG.info(log_json(msg="Partition dropped during verification", context=self.context))
                    return
                else:
                    LOG.warning(log_json(msg="Trino external error", context=self.context), exc_info=te)
                    return
            except Exception as err:
                LOG.warning(log_json(msg="data validation trino query failed", context=self.context), exc_info=err)
                return
            # Compare results
            LOG.debug(f"PG: {pg_data} Trino data: {trino_data}")
            daily_difference, valid_cost = self.compare_data(pg_data, trino_data)
            if valid_cost:
                LOG.info(log_json(msg="all data complete for provider", context=self.context))
            else:
                LOG.error(
                    log_json(
                        msg="provider has incomplete data for specified days",
                        daily_difference=str(daily_difference),
                        context=self.context,
                    )
                )
