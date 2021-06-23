#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes report data from database."""
import logging
from datetime import date
from datetime import datetime

from tenant_schemas.utils import schema_context

from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.koku_database_access import mini_transaction_delete
from reporting.models import PartitionedTable


LOG = logging.getLogger(__name__)


class GCPReportDBCleanerError(Exception):
    """Raise an error during GCP report cleaning."""


class GCPReportDBCleaner:
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
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        LOG.info("Calling purge_expired_line_item for gcp")
        if not isinstance(expired_date, datetime):
            err = "Parameter expired_date must be a datetime.datetime object."
            raise GCPReportDBCleanerError(err)

        with GCPReportDBAccessor(self._schema) as accessor:
            removed_items = []
            if provider_uuid is not None:
                bill_objects = accessor.get_bill_query_before_date(expired_date, provider_uuid)
            else:
                bill_objects = accessor.get_bill_query_before_date(expired_date)
            with schema_context(self._schema):
                for bill in bill_objects.all():
                    bill_id = bill.id
                    removed_provider_uuid = bill.provider_id
                    removed_billing_period_start = bill.billing_period_start

                    if not simulate:
                        lineitem_query = accessor.get_lineitem_query_for_billid(bill_id)
                        del_count, remainder = mini_transaction_delete(lineitem_query)
                        LOG.info("Removing %s cost entry line items for bill id %s", del_count, bill_id)

                    LOG.info(
                        "Line item data removed for Provider ID: %s with billing period: %s",
                        removed_provider_uuid,
                        removed_billing_period_start,
                    )
                    removed_items.append(
                        {
                            "removed_provider_uuid": removed_provider_uuid,
                            "billing_period_start": str(removed_billing_period_start),
                        }
                    )
        return removed_items

    def purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False):
        """Remove report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        LOG.info("Calling purge_expired_report_data for gcp")

        with GCPReportDBAccessor(self._schema) as accessor:
            if (expired_date is None and provider_uuid is None) or (  # noqa: W504
                expired_date is not None and provider_uuid is not None
            ):
                err = "This method must be called with either expired_date or provider_uuid"
                raise GCPReportDBCleanerError(err)
            removed_items = []

            if expired_date is not None:
                return self.purge_expired_report_data_by_date(expired_date, simulate=simulate)
            else:
                bill_objects = accessor.get_cost_entry_bills_query_by_provider(provider_uuid)
            with schema_context(self._schema):
                for bill in bill_objects.all():
                    bill_id = bill.id
                    removed_provider_uuid = bill.provider_id
                    removed_billing_period_start = bill.billing_period_start

                    if not simulate:
                        del_count = accessor.execute_delete_sql(accessor.get_lineitem_query_for_billid(bill_id))
                        LOG.info("Removing %s cost entry line items for bill id %s", del_count, bill_id)

                        del_count = accessor.execute_delete_sql(accessor.get_daily_query_for_billid(bill_id))
                        LOG.info("Removing %s cost entry daily items for bill id %s", del_count, bill_id)

                        del_count = accessor.execute_delete_sql(accessor.get_summary_query_for_billid(bill_id))
                        LOG.info("Removing %s cost entry summary items for bill id %s", del_count, bill_id)

                    LOG.info(
                        "Report data removed for Provider ID: %s with billing period: %s",
                        removed_provider_uuid,
                        removed_billing_period_start,
                    )
                    removed_items.append(
                        {
                            "removed_provider_uuid": removed_provider_uuid,
                            "billing_period_start": str(removed_billing_period_start),
                        }
                    )

                if not simulate:
                    bill_objects.delete()

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        paritition_from = str(date(expired_date.year, expired_date.month, 1))
        with GCPReportDBAccessor(self._schema) as accessor:
            all_bill_objects = accessor.get_bill_query_before_date(expired_date).all()
            table_names = [
                # accessor._table_map["ocp_on_gcp_daily_summary"],
                # accessor._table_map["ocp_on_gcp_project_daily_summary"],
                accessor.line_item_daily_summary_table._meta.db_table
            ]
            base_lineitem_query = accessor._get_db_obj_query(accessor.line_item_table)
            base_daily_query = accessor._get_db_obj_query(accessor.line_item_daily_table)

        with schema_context(self._schema):
            removed_items = []
            if not simulate:
                # Will call trigger to detach, truncate, and drop partitions
                del_count = PartitionedTable.objects.filter(
                    schema_name=self._schema,
                    partition_of_table_name__in=table_names,
                    partition_parameters__default=False,
                    partition_parameters__from__lte=paritition_from,
                ).delete()
                LOG.info(f"Deleted {del_count} table partitions total for the following tables: {table_names}")

                # Iterate over the remainder as they could involve much larger amounts of data
            for bill in all_bill_objects:
                if not simulate:
                    del_count = base_lineitem_query.filter(cost_entry_bill_id=bill.id).delete()
                    LOG.info(f"Deleted {del_count} cost entry line items for bill_id {bill.id}")

                    del_count = base_daily_query.filter(cost_entry_bill_id=bill.id).delete()
                    LOG.info(f"Deleted {del_count} cost entry line items for bill_id {bill.id}")

                removed_items.append(
                    {"removed_provider_uuid": bill.provider_id, "billing_period_start": str(bill.billing_period_start)}
                )
                LOG.info(
                    f"Report data deleted for account payer id {bill.provider_id} "
                    f"and billing period {bill.billing_period_start}"
                )

        return removed_items
