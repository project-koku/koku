#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from datetime import datetime

from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database import OCI_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.common import date_range_pair
from reporting.provider.aws.models import TRINO_LINE_ITEM_DAILY_TABLE as AWS_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.azure.models import TRINO_LINE_ITEM_DAILY_TABLE as AZURE_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import TRINO_LINE_ITEM_DAILY_TABLE as GCP_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.oci.models import TRINO_LINE_ITEM_DAILY_TABLE_MAP as OCI_TRINO_LINE_ITEM_DAILY_TABLE

LOG = logging.getLogger(__name__)

# Filter maps
TRINO_FILTER_MAP = {
    Provider.PROVIDER_AWS: {"date": "lineitem_usagestartdate", "metric": "lineitem_unblendedcost"},
    Provider.PROVIDER_AZURE: {"date": "date", "metric": "coalesce(nullif(costinbillingcurrency, 0), pretaxcost)"},
    Provider.PROVIDER_GCP: {"date": "usage_start_time", "metric": "cost"},
    Provider.PROVIDER_OCI: {"date": "lineitem_intervalusagestart", "metric": "cost_mycost"},
    Provider.PROVIDER_OCP: {
        "date": "usage_start",
        "metric": "pod_usage_cpu_core_hours",
    },
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
    Provider.PROVIDER_OCI: {"date": "usage_start", "metric": "cost"},
    Provider.PROVIDER_OCP: {
        "date": "usage_start",
        "metric": "pod_usage_cpu_core_hours",
    },
}

# Table maps
PG_TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_CUR_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_AZURE: AZURE_REPORT_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_GCP: GCP_REPORT_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_OCI: OCI_CUR_TABLE_MAP.get("line_item_daily_summary"),
    Provider.PROVIDER_OCP: OCP_REPORT_TABLE_MAP.get("line_item_daily_summary"),
    "OCPAWS": AWS_CUR_TABLE_MAP.get("ocp_on_aws_project_daily_summary"),
    "OCPAZURE": AZURE_REPORT_TABLE_MAP.get("ocp_on_aws_project_daily_summary"),
    "OCPGCP": GCP_REPORT_TABLE_MAP.get("ocp_on_aws_project_daily_summary"),
}

TRINO_TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_AZURE: AZURE_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_GCP: GCP_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_OCI: OCI_TRINO_LINE_ITEM_DAILY_TABLE.get("cost"),
    Provider.PROVIDER_OCP: "reporting_ocpusagelineitem_daily_summary",
    "OCPAWS": "reporting_ocpawscostlineitem_project_daily_summary",
    "OCPAZURE": "reporting_ocpazurecostlineitem_project_daily_summary",
    "OCPGCP": "reporting_ocpgcpcostlineitem_project_daily_summary",
}


class QueryError(Exception):
    """Errors specific to Trino query"""

    pass


def get_table_filters_for_provider(provider_type, trino=False):
    """Get relevant table and query filters for given provider type"""
    table = PG_TABLE_MAP.get(provider_type)
    query_filters = PG_FILTER_MAP.get(provider_type)
    if trino:
        table = TRINO_TABLE_MAP.get(provider_type)
        query_filters = TRINO_FILTER_MAP.get(provider_type)
    return table, query_filters


def data_validation(pg_data, trino_data, tolerance=1):
    """Validate if postgres and trino query data cost matches per day"""
    incomplete_days = {}
    valid_cost = True
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


def execute_relevant_query(schema, provider_uuid, provider_type, start_date, end_date, date_step, trino=False):
    # query trino/postgres
    table, query_filters = get_table_filters_for_provider(provider_type, trino)
    report_db_accessor = ReportDBAccessorBase(schema)
    daily_result = {}
    dh = DateHelper()
    year = dh.bill_year_from_date(start_date)
    month = dh.bill_month_from_date(start_date)
    for start, end in date_range_pair(start_date, end_date, step=date_step):
        if trino:
            sql = f"""
                SELECT sum({query_filters.get("metric")}) as metric, {query_filters.get("date")} as date FROM hive.{schema}.{table}
                    WHERE source = '{provider_uuid}'
                    AND {query_filters.get("date")} >= date('{start}')
                    AND {query_filters.get("date")} <= date('{end}')
                    AND year = '{year}'
                    AND month = '{month}'
                    GROUP BY {query_filters.get("date")}
                    ORDER BY {query_filters.get("date")}"""
            result = report_db_accessor._execute_trino_raw_sql_query(sql, log_ref="data validation query")
        else:
            sql = f"""
                SELECT sum({query_filters.get("metric")}) as metric, {query_filters.get("date")} as date FROM {schema}.{table}_{year}_{month}
                    WHERE source_uuid = '{provider_uuid}'
                    AND {query_filters.get("date")} >= '{start}'
                    AND {query_filters.get("date")} <= '{end}'
                    GROUP BY {query_filters.get("date")}
                    ORDER BY {query_filters.get("date")}"""
            result = report_db_accessor._prepare_and_execute_raw_sql_query(
                query_filters.get("table"), sql, operation="VALIDATION_QUERY"
            )
        if result != []:
            for day in result:
                key = day[1].date() if isinstance(day[1], datetime) else day[1]
                daily_result[key] = float(day[0])
    return daily_result


def check_data_integrity(schema, provider_uuid, start_date, end_date, context, date_step=settings.TRINO_DATE_STEP):
    valid_cost = False
    pg_data = None
    trino_data = None
    daily_difference = {}
    LOG.info(log_json(msg=f"validation started for provider: {provider_uuid}", context=context))
    provider = Provider.objects.filter(uuid=provider_uuid).first()
    # Postgres query to get daily cost
    try:
        pg_data = execute_relevant_query(
            schema, provider_uuid, provider.type.strip("-local"), start_date, end_date, date_step
        )
    except Exception as e:
        LOG.warning(log_json(msg=f"data validation postgres query failed: {e}", context=context))
        return QueryError
    # Trino query to get daily cost
    try:
        trino_data = execute_relevant_query(
            schema, provider_uuid, provider.type.strip("-local"), start_date, end_date, date_step, True
        )
    except Exception as e:
        LOG.warning(log_json(msg=f"data validation trino query failed: {e}", context=context))
        return QueryError
    # Compare results, looking for discrepency in cost
    daily_difference, valid_cost = data_validation(pg_data, trino_data)
    if valid_cost:
        LOG.info(log_json(msg=f"all data complete for provider: {provider_uuid}", context=context))
        provider.data_valid = True
    else:
        LOG.warning(
            log_json(msg=f"provider has incomplete data for specified days: {daily_difference}", context=context)
        )
        provider.data_valid = False
    # update provider object with validation state
    provider.save(update_fields=["data_valid"])
