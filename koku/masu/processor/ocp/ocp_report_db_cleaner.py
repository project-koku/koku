#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes report data from database."""
import logging
from datetime import date

from tenant_schemas.utils import schema_context

from koku.database import cascade_delete
from koku.database import execute_delete_sql
from koku.database import get_model
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.models import PartitionedTable
from reporting.provider.ocp.models import UI_SUMMARY_TABLES

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
        LOG.info("Calling purge_expired_report_data for ocp")

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

            with schema_context(self._schema):
                for usage_period in usage_period_objs.all():
                    removed_items.append(
                        {"usage_period_id": usage_period.id, "interval_start": str(usage_period.report_period_start)}
                    )
                    all_report_periods.append(usage_period.id)
                    all_cluster_ids.add(usage_period.cluster_id)
                    all_period_starts.add(str(usage_period.report_period_start))

                all_report_periods.sort()
                LOG.info(
                    f"Removing all data related to report_period_ids: {all_report_periods}; "
                    f"cluster_ids: {sorted(all_cluster_ids)}; starting periods {sorted(all_period_starts)}"
                )

                if not simulate:
                    cascade_delete(usage_period_objs.query.model, usage_period_objs)

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        LOG.info("Executing purge_expired_report_data_by_date")
        partition_from = str(date(expired_date.year, expired_date.month, 1))
        removed_items = []
        all_report_periods = []
        all_cluster_ids = set()
        all_period_starts = set()

        with OCPReportDBAccessor(self._schema) as accessor:
            # all_usage_periods = accessor.get_usage_periods_by_date(expired_date)
            all_usage_periods = accessor._get_db_obj_query(accessor._table_map["report_period"]).filter(
                report_period_start__lte=expired_date
            )

            table_names = [
                # accessor._aws_table_map["ocp_on_aws_daily_summary"],
                # accessor._aws_table_map["ocp_on_aws_project_daily_summary"],
                accessor._table_map["line_item_daily_summary"]
            ]
            table_names.extend(UI_SUMMARY_TABLES)
            table_models = [get_model(tn) for tn in table_names]

        with schema_context(self._schema):
            # Iterate over the remainder as they could involve much larger amounts of data
            for usage_period in all_usage_periods:
                removed_items.append(
                    {"usage_period_id": usage_period.id, "interval_start": str(usage_period.report_period_start)}
                )
                all_report_periods.append(usage_period.id)
                all_cluster_ids.add(usage_period.cluster_id)
                all_period_starts.add(str(usage_period.report_period_start))

            all_report_periods.sort()
            LOG.info(
                f"Removing all data related to "
                f"cluster_ids: {sorted(all_cluster_ids)}; starting periods {sorted(all_period_starts)}"
            )

            if not simulate:
                # Will call trigger to detach, truncate, and drop partitions
                LOG.info(
                    "Deleting table partitions total for the following tables: "
                    + f"{table_names} with partitions <= {partition_from}"
                )
                del_count = execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=self._schema,
                        partition_of_table_name__in=table_names,
                        partition_parameters__default=False,
                        partition_parameters__from__lte=partition_from,
                    )
                )
                LOG.info(f"Deleted {del_count} table partitions")

            if not simulate:
                cascade_delete(all_usage_periods.query.model, all_usage_periods, skip_relations=table_models)

        return removed_items
