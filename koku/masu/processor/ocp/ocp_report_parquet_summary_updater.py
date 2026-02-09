#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import logging
from datetime import datetime

import ciso8601
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from api.utils import DateHelper
from koku.pg_partition import PartitionHandlerMixin
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.util.common import date_range_pair
from masu.util.common import SummaryRangeConfig
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.ocp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class OCPReportParquetSummaryUpdaterClusterNotFound(Exception):
    pass


class OCPReportParquetSummaryUpdater(PartitionHandlerMixin):
    """Class to update OCP report summary data from Trino/Parquet data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema
        self._provider = provider
        self._manifest = manifest

        self._cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        if not self._cluster_id:
            msg = "missing cluster_id for provider"
            LOG.warning(log_json(msg=msg, provider_uuid=provider.uuid, schema=schema))
            raise OCPReportParquetSummaryUpdaterClusterNotFound(msg)

        self._cluster_alias = get_cluster_alias_from_cluster_id(self._cluster_id)
        self._context = {
            "schema": self._schema,
            "provider_uuid": self._provider.uuid,
            "cluster_id": self._cluster_id,
            "cluster_alias": self._cluster_alias,
        }

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""

        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()

        return start_date, end_date

    def _check_parquet_date_range(self, start_date, end_date):
        """Make sure we don't summarize for a date range we don't have data for."""
        start_datetime = datetime(start_date.year, start_date.month, start_date.day)
        with OCPReportDBAccessor(self._schema) as accessor:
            min_timestamp, __ = accessor.get_max_min_timestamp_from_parquet(self._provider.uuid, start_date, end_date)
            if min_timestamp > start_datetime:
                start_date = min_timestamp.date()
        return start_date, end_date

    def update_summary_tables(self, start_date, end_date, **kwargs):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)
        start_date, end_date = self._check_parquet_date_range(start_date, end_date)

        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        with OCPReportDBAccessor(self._schema) as accessor:
            with schema_context(self._schema):
                report_period = accessor.report_periods_for_provider_uuid(self._provider.uuid, start_date)
                if not report_period:
                    LOG.warning(
                        log_json(
                            msg="no report period found for start_date",
                            start_date=start_date,
                            end_date=end_date,
                            context=self._context,
                        )
                    )
                    return start_date, end_date
                report_period_id = report_period.id

            accessor.populate_openshift_cluster_information_tables(
                self._provider, self._cluster_id, self._cluster_alias, start_date, end_date
            )

            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    log_json(
                        msg="updating OCP report summary tables",
                        context=self._context,
                        start_date=start,
                        end_date=end,
                        report_period_id=report_period_id,
                    )
                )
                # This will process POD and STORAGE together
                # "delete_all_except_infrastructure_raw_cost_from_daily_summary" specificallly excludes
                # the cost rows generated through the OCPCloudParquetReportSummaryUpdater
                accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary(
                    self._provider.uuid, report_period_id, start, end
                )
                accessor.populate_line_item_daily_summary_table_trino(
                    start, end, report_period_id, self._cluster_id, self._cluster_alias, self._provider.uuid
                )
                accessor.populate_ui_summary_tables(
                    SummaryRangeConfig(start_date=start, end_date=end), self._provider.uuid
                )

            # This will process POD and STORAGE together
            LOG.info(
                log_json(
                    msg="updating OCP label summary tables",
                    context=self._context,
                    start_date=start_date,
                    end_date=end_date,
                    report_period_id=report_period_id,
                )
            )
            accessor.populate_pod_label_summary_table([report_period_id], start_date, end_date)
            accessor.populate_volume_label_summary_table([report_period_id], start_date, end_date)
            accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, [report_period_id])

            LOG.info(
                log_json(msg="updating OCP report periods", context=self._context, report_period_id=report_period_id)
            )
            if report_period.summary_data_creation_datetime is None:
                report_period.summary_data_creation_datetime = timezone.now()
            report_period.summary_data_updated_datetime = timezone.now()
            report_period.save()
            LOG.info(
                log_json(
                    msg="updated OCP report periods",
                    created=report_period.summary_data_creation_datetime,
                    updated=report_period.summary_data_updated_datetime,
                    context=self._context,
                    report_period_id=report_period_id,
                )
            )

            self.check_cluster_infrastructure(start_date, end_date)

        return start_date, end_date

    def check_cluster_infrastructure(self, start_date, end_date):
        # Override start date so we map with a more complete dataset
        start_date = DateHelper().month_start(start_date)
        LOG.info(
            log_json(
                msg="checking if OCP cluster is running on cloud infrastructure",
                context=self._context,
                start_date=start_date,
                end_date=end_date,
            )
        )

        updater_base = OCPCloudUpdaterBase(self._schema, self._provider, self._manifest)
        if (
            infra_map := updater_base.get_infra_map_from_providers()
            or updater_base._generate_ocp_infra_map_from_sql_trino(start_date, end_date)
        ):
            for ocp_source, infra_tuple in infra_map.items():
                LOG.info(
                    log_json(
                        msg="OCP cluster is running on cloud infrastructure",
                        context=self._context,
                        ocp_provider_uuid=ocp_source,
                        infra_provider_uuid=infra_tuple[0],
                        infra_provider_type=infra_tuple[1],
                    )
                )
