#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Update OCP summary tables using PostgreSQL-based pipeline."""
import logging

import ciso8601
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from api.utils import DateHelper
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.util.common import date_range_pair
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.ocp.models import UI_SUMMARY_TABLES
from reporting_common.models import PartitionHandlerMixin

LOG = logging.getLogger(__name__)


class OCPPostgresSummaryUpdaterClusterNotFound(Exception):
    """Exception for missing cluster ID."""

    pass


class OCPPostgresSummaryUpdater(PartitionHandlerMixin):
    """Update OCP report summary data from PostgreSQL staging tables."""

    def __init__(self, schema, provider, manifest):
        """Initialize the updater.

        Args:
            schema (str): The customer schema
            provider (Provider): The provider object
            manifest (CostUsageReportManifest): The manifest object
        """
        self._schema = schema
        self._provider = provider
        self._manifest = manifest

        self._cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        if not self._cluster_id:
            msg = "missing cluster_id for provider"
            LOG.warning(log_json(msg=msg, provider_uuid=provider.uuid, schema=schema))
            raise OCPPostgresSummaryUpdaterClusterNotFound(msg)

        self._cluster_alias = get_cluster_alias_from_cluster_id(self._cluster_id)
        self._context = {
            "schema": self._schema,
            "provider_uuid": str(self._provider.uuid),
            "cluster_id": self._cluster_id,
            "cluster_alias": self._cluster_alias,
            "pipeline": "postgres",
        }

    def _get_sql_inputs(self, start_date, end_date):
        """Convert date inputs to proper format.

        Args:
            start_date (str|date): Start date
            end_date (str|date): End date

        Returns:
            tuple: (start_date, end_date) as date objects
        """
        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()

        return start_date, end_date

    def _check_staging_data_exists(self, start_date, end_date):
        """Check if staging data exists for the date range.

        Args:
            start_date (date): Start date
            end_date (date): End date

        Returns:
            bool: True if staging data exists
        """
        with OCPReportDBAccessor(self._schema) as accessor:
            # Check if any staging tables have data for this date range
            staging_tables = [
                "reporting_ocpusagelineitem_pod_staging",
                "reporting_ocpusagelineitem_storage_staging",
                "reporting_ocpusagelineitem_node_labels_staging",
                "reporting_ocpusagelineitem_namespace_labels_staging",
            ]

            for table in staging_tables:
                query = f"""
                    SELECT EXISTS(
                        SELECT 1 FROM {self._schema}.{table}
                        WHERE interval_start >= %s
                          AND interval_start < %s + interval '1 day'
                          AND source_uuid = %s
                          AND processed = false
                    )
                """
                with accessor._get_db_obj_query().connection.cursor() as cursor:
                    cursor.execute(query, [start_date, end_date, str(self._provider.uuid)])
                    exists = cursor.fetchone()[0]
                    if exists:
                        return True

        return False

    def update_summary_tables(self, start_date, end_date, **kwargs):
        """Populate the summary tables for reporting.

        Args:
            start_date (str|date): The date to start populating
            end_date (str|date): The date to end on

        Returns:
            tuple: (start_date, end_date) as date objects
        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)

        LOG.info(
            log_json(
                msg="starting PostgreSQL-based OCP summary update",
                context=self._context,
                start_date=str(start_date),
                end_date=str(end_date),
            )
        )

        # Check if staging data exists
        if not self._check_staging_data_exists(start_date, end_date):
            LOG.info(
                log_json(
                    msg="no unprocessed staging data found, skipping",
                    context=self._context,
                    start_date=str(start_date),
                    end_date=str(end_date),
                )
            )
            return start_date, end_date

        # Handle partitions for UI summary tables
        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        with OCPReportDBAccessor(self._schema) as accessor:
            with schema_context(self._schema):
                # Get report period
                report_period = accessor.report_periods_for_provider_uuid(self._provider.uuid, start_date)
                if not report_period:
                    LOG.warning(
                        log_json(
                            msg="no report period found for start_date",
                            start_date=str(start_date),
                            end_date=str(end_date),
                            context=self._context,
                        )
                    )
                    return start_date, end_date
                report_period_id = report_period.id

            # Populate cluster information tables
            accessor.populate_openshift_cluster_information_tables(
                self._provider, self._cluster_id, self._cluster_alias, start_date, end_date
            )

            # Process in date chunks (same step size as Trino pipeline for consistency)
            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    log_json(
                        msg="updating OCP report summary tables via PostgreSQL",
                        context=self._context,
                        start_date=str(start),
                        end_date=str(end),
                        report_period_id=report_period_id,
                    )
                )

                # Call PostgreSQL aggregation function
                accessor.populate_daily_summary_from_staging(
                    start, end, report_period_id, self._cluster_id, self._cluster_alias, self._provider.uuid
                )

                # Populate UI summary tables (same as Trino pipeline)
                accessor.populate_ui_summary_tables(start, end, self._provider.uuid)

            # Populate label summary tables
            LOG.info(
                log_json(
                    msg="updating OCP label summary tables",
                    context=self._context,
                    start_date=str(start_date),
                    end_date=str(end_date),
                    report_period_id=report_period_id,
                )
            )
            accessor.populate_pod_label_summary_table([report_period_id], start_date, end_date)
            accessor.populate_volume_label_summary_table([report_period_id], start_date, end_date)
            accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, [report_period_id])

            # Update report period timestamps
            LOG.info(
                log_json(
                    msg="updating OCP report periods",
                    context=self._context,
                    report_period_id=report_period_id,
                )
            )
            if report_period.summary_data_creation_datetime is None:
                report_period.summary_data_creation_datetime = timezone.now()
            report_period.summary_data_updated_datetime = timezone.now()
            report_period.save()
            LOG.info(
                log_json(
                    msg="updated OCP report periods",
                    created=str(report_period.summary_data_creation_datetime),
                    updated=str(report_period.summary_data_updated_datetime),
                    context=self._context,
                    report_period_id=report_period_id,
                )
            )

            # Check for cloud infrastructure (OCP-on-AWS/Azure/GCP)
            self.check_cluster_infrastructure(start_date, end_date)

        LOG.info(
            log_json(
                msg="PostgreSQL-based OCP summary update completed",
                context=self._context,
                start_date=str(start_date),
                end_date=str(end_date),
            )
        )

        return start_date, end_date

    def check_cluster_infrastructure(self, start_date, end_date):
        """Check if OCP cluster is running on cloud infrastructure.

        Args:
            start_date (date): Start date
            end_date (date): End date
        """
        # Override start date to use month start for complete dataset
        start_date = DateHelper().month_start(start_date)

        LOG.info(
            log_json(
                msg="checking if OCP cluster is running on cloud infrastructure",
                context=self._context,
                start_date=str(start_date),
                end_date=str(end_date),
            )
        )

        updater_base = OCPCloudUpdaterBase(self._schema, self._provider, self._manifest)

        # Get infrastructure mapping from provider relationships or Trino query
        # Note: OCP-on-Cloud matching still uses Trino as it queries cloud provider Parquet data
        infra_map = updater_base.get_infra_map_from_providers() or updater_base._generate_ocp_infra_map_from_sql_trino(
            start_date, end_date
        )

        if infra_map:
            for ocp_source, infra_tuple in infra_map.items():
                LOG.info(
                    log_json(
                        msg="OCP cluster is running on cloud infrastructure",
                        context=self._context,
                        ocp_provider_uuid=str(ocp_source),
                        infra_provider_uuid=str(infra_tuple[0]),
                        infra_provider_type=infra_tuple[1],
                    )
                )

                # Trigger OCP-on-Cloud summarization
                updater_base.update_summary_tables(ocp_source, infra_tuple[0], infra_tuple[1], start_date, end_date)
        else:
            LOG.info(
                log_json(
                    msg="OCP cluster not running on cloud infrastructure or no matching data found",
                    context=self._context,
                )
            )
