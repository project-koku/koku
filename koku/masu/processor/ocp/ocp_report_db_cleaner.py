#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes report data from database."""
import logging
from datetime import datetime

from tenant_schemas.utils import schema_context

from masu.database.koku_database_access import mini_transaction_delete
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor

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

    def purge_expired_line_item(self, expired_date, provider_uuid=None, simulate=False):
        """Remove raw line item report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'usage_period_id' and 'interval_start'

        """
        LOG.info("Calling purge_expired_line_item for ocp")
        if not isinstance(expired_date, datetime):
            err = "Parameter expired_date must be a datetime.datetime object."
            raise OCPReportDBCleanerError(err)

        with OCPReportDBAccessor(self._schema) as accessor:
            removed_items = []
            if provider_uuid is not None:
                usage_period_objs = accessor.get_usage_period_on_or_before_date(expired_date, provider_uuid)
            else:
                usage_period_objs = accessor.get_usage_period_on_or_before_date(expired_date)
            with schema_context(self._schema):
                for usage_period in usage_period_objs.all():
                    report_period_id = usage_period.id
                    removed_usage_start_period = usage_period.report_period_start

                    if not simulate:
                        item_query = accessor.get_item_query_report_period_id(report_period_id)
                        qty, remainder = mini_transaction_delete(item_query)
                        LOG.info("Removing %s usage period line items for usage period id %s", qty, report_period_id)

                    LOG.info(
                        "Line item data removed for usage period ID: %s with interval start: %s",
                        report_period_id,
                        removed_usage_start_period,
                    )
                    removed_items.append(
                        {"usage_period_id": report_period_id, "interval_start": str(removed_usage_start_period)}
                    )
        return removed_items

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

            if expired_date is not None:
                usage_period_objs = accessor.get_usage_period_on_or_before_date(expired_date)
            else:
                usage_period_objs = accessor.get_usage_period_query_by_provider(provider_uuid)
            with schema_context(self._schema):
                for usage_period in usage_period_objs.all():
                    report_period_id = usage_period.id
                    cluster_id = usage_period.cluster_id
                    removed_usage_start_period = usage_period.report_period_start

                    if not simulate:
                        qty = accessor.get_item_query_report_period_id(report_period_id).delete()
                        LOG.info("Removing %s usage period line items for usage period id %s", qty, report_period_id)

                        qty = accessor.get_daily_usage_query_for_clusterid(cluster_id).delete()
                        LOG.info("Removing %s usage daily items for cluster id %s", qty, cluster_id)

                        qty = accessor.get_summary_usage_query_for_clusterid(cluster_id).delete()
                        LOG.info("Removing %s usage summary items for cluster id %s", qty, cluster_id)

                        qty = accessor.get_cost_summary_for_clusterid(cluster_id).delete()
                        LOG.info("Removing %s cost summary items for cluster id %s", qty, cluster_id)

                        qty = accessor.get_storage_item_query_report_period_id(report_period_id).delete()
                        LOG.info("Removing %s storage line items for usage period id %s", qty, report_period_id)

                        qty = accessor.get_node_label_item_query_report_period_id(report_period_id).delete()
                        LOG.info("Removing %s node label line items for usage period id %s", qty, report_period_id)

                        qty = accessor.get_daily_storage_item_query_cluster_id(cluster_id).delete()
                        LOG.info("Removing %s storage dailyitems for cluster id %s", qty, cluster_id)

                        qty = accessor.get_storage_summary_query_cluster_id(cluster_id).delete()
                        LOG.info("Removing %s storage summary for cluster id %s", qty, cluster_id)

                        qty = accessor.get_report_query_report_period_id(report_period_id).delete()
                        LOG.info("Removing %s usage period items for usage period id %s", qty, report_period_id)

                        qty = accessor.get_ocp_aws_summary_query_for_cluster_id(cluster_id).delete()
                        LOG.info("Removing %s OCP-on-AWS summary items for cluster id %s", qty, cluster_id)

                        qty = accessor.get_ocp_aws_project_summary_query_for_cluster_id(cluster_id).delete()
                        LOG.info("Removing %s OCP-on-AWS project summary items for cluster id %s", qty, cluster_id)

                    LOG.info(
                        "Report data removed for usage period ID: %s with interval start: %s",
                        report_period_id,
                        removed_usage_start_period,
                    )
                    removed_items.append(
                        {"usage_period_id": report_period_id, "interval_start": str(removed_usage_start_period)}
                    )

                if not simulate:
                    usage_period_objs.delete()
        return removed_items
