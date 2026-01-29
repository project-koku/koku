#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes report data from database."""
import logging
from datetime import date

from django.conf import settings

from api.common import log_json
from koku.database import cascade_delete
from koku.database import execute_delete_sql
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.models import PartitionedTable
from reporting.models import TRINO_MANAGED_TABLES
from reporting.provider.ocp.models import UI_SUMMARY_TABLES
from reporting.provider.ocp.self_hosted_models import get_self_hosted_table_names

LOG = logging.getLogger(__name__)


class OCPReportDBCleanerError(Exception):
    """Raise an error during OCP report cleaning."""


class OCPReportDBCleaner:
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema

    def purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False):
        """Remove usage data with a report period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'usage_period_id' and 'interval_start'

        """
        LOG.info(log_json(msg="calling purge_expired_report_data for OCP"))

        with OCPReportDBAccessor(self._schema) as accessor:
            if (expired_date is not None and provider_uuid is not None) or (  # noqa: W504
                expired_date is None and provider_uuid is None
            ):
                err = "This method must be called with expired_date or provider_uuid"
                raise OCPReportDBCleanerError(err)
            removed_items = []
            all_report_periods = []
            all_cluster_ids = set()
            all_period_starts = set()

            if expired_date is not None:
                return self.purge_expired_report_data_by_date(expired_date, simulate=simulate)

            usage_period_objs = accessor.get_usage_period_query_by_provider(provider_uuid)
            for usage_period in usage_period_objs.all():
                removed_items.append(
                    {"usage_period_id": usage_period.id, "interval_start": str(usage_period.report_period_start)}
                )
                all_report_periods.append(usage_period.id)
                all_cluster_ids.add(usage_period.cluster_id)
                all_period_starts.add(str(usage_period.report_period_start))

            LOG.info(
                log_json(
                    msg="deleting provider billing data",
                    schema=self._schema,
                    provider_uuid=provider_uuid,
                    report_periods=all_report_periods,
                    cluster_ids=all_cluster_ids,
                    period_starts=all_period_starts,
                )
            )

            if not simulate:
                cascade_delete(usage_period_objs.query.model, usage_period_objs)

                # For on-prem, also delete from self-hosted tables
                if settings.ONPREM:
                    accessor.delete_self_hosted_data_by_source(provider_uuid)

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        LOG.info(log_json(msg="executing purge_expired_report_data_by_date"))
        partition_from = str(date(expired_date.year, expired_date.month, 1))
        removed_items = []
        all_report_periods = []

        with OCPReportDBAccessor(self._schema) as accessor:
            all_usage_periods = accessor.get_report_periods_before_date(expired_date)

            table_names = [
                # accessor._aws_table_map["ocp_on_aws_daily_summary"],
                # accessor._aws_table_map["ocp_on_aws_project_daily_summary"],
                accessor._table_map["line_item_daily_summary"]
            ]
            table_names.extend(UI_SUMMARY_TABLES)

            # For on-prem, include self-hosted line item tables in partition cleanup
            if settings.ONPREM:
                table_names.extend(get_self_hosted_table_names())

            # Iterate over the remainder as they could involve much larger amounts of data
            for usage_period in all_usage_periods:
                removed_items.append(
                    {"usage_period_id": usage_period.id, "interval_start": str(usage_period.report_period_start)}
                )
                all_report_periods.append(usage_period.id)

            if not simulate:
                # Will call trigger to detach, truncate, and drop partitions
                LOG.info(
                    log_json(
                        msg="deleting table partitions total for tables",
                        tables=table_names,
                        partitions=partition_from,
                    )
                )
                del_count = execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=self._schema,
                        partition_of_table_name__in=table_names,
                        partition_parameters__default=False,
                        partition_parameters__from__lte=partition_from,
                    )
                )
                LOG.info(log_json(msg="deleted table partitions", count=del_count, schema=self._schema))

                # Remove all data related to the report period
                cascade_delete(all_usage_periods.query.model, all_usage_periods)
                LOG.info(
                    log_json(
                        msg="deleted ocp-usage-report-periods",
                        report_periods=all_report_periods,
                        schema=self._schema,
                    )
                )

        return removed_items

    def purge_expired_trino_partitions(self, expired_date, simulate=False):
        """Removes expired trino partitions."""
        LOG.debug(f"purge_expired_trino_partitions: {expired_date}, {simulate}")

        with OCPReportDBAccessor(self._schema) as accessor:
            for table, source_column in TRINO_MANAGED_TABLES.items():
                LOG.debug(f"{table}, {source_column}")
                results = accessor.find_expired_trino_partitions(table, source_column, str(expired_date.date()))
                if results:
                    LOG.info(f"Discovered {len(results)} expired partitions")
                else:
                    LOG.info("No expired partitions")
                    return
                for partition in results:
                    LOG.info(f"partition_info: {partition}")
                    if not simulate:
                        year, month, source_value = partition
                        accessor.delete_hive_partition_by_month(table, source_value, year, month, source_column)
