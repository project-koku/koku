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
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from reporting.models import PartitionedTable
from reporting.provider.azure.models import UI_SUMMARY_TABLES


LOG = logging.getLogger(__name__)


class AzureReportDBCleanerError(Exception):
    """Raise an error during AWS report cleaning."""


class AzureReportDBCleaner:
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema

    def purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False):
        """Remove report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simulate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        LOG.info("Calling purge_expired_report_data for azure")

        with AzureReportDBAccessor(self._schema) as accessor:
            if (expired_date is None and provider_uuid is None) or (  # noqa: W504
                expired_date is not None and provider_uuid is not None
            ):
                err = "This method must be called with either expired_date or provider_uuid"
                raise AzureReportDBCleanerError(err)
            removed_items = []
            all_providers = set()
            all_period_starts = set()

            if expired_date is not None:
                return self.purge_expired_report_data_by_date(expired_date, simulate=simulate)

            bill_objects = accessor.get_cost_entry_bills_query_by_provider(provider_uuid)

        with schema_context(self._schema):
            for bill in bill_objects.all():
                removed_items.append(
                    {"provider_uuid": bill.provider_id, "billing_period_start": str(bill.billing_period_start)}
                )
                all_providers.add(bill.provider_id)
                all_period_starts.add(str(bill.billing_period_start))

            LOG.info(f"Deleting data for providers {sorted(all_providers)} and periods {sorted(all_period_starts)}")

            if not simulate:
                cascade_delete(bill_objects.query.model, bill_objects)

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        partition_from = str(date(expired_date.year, expired_date.month, 1))
        with AzureReportDBAccessor(self._schema) as accessor:
            all_bill_objects = accessor.get_bill_query_before_date(expired_date).all()
            table_names = [
                # accessor._table_map["ocp_on_azure_daily_summary"],
                # accessor._table_map["ocp_on_azure_project_daily_summary"],
                accessor.line_item_daily_summary_table._meta.db_table,
                accessor.ocpall_line_item_daily_summary_table._meta.db_table,
                accessor.ocpall_line_item_project_daily_summary_table._meta.db_table,
            ]
            table_names.extend(UI_SUMMARY_TABLES)
            table_models = [get_model(tn) for tn in table_names]

        with schema_context(self._schema):
            removed_items = []
            all_providers = set()
            all_period_starts = set()

            # Iterate over the remainder as they could involve much larger amounts of data
            for bill in all_bill_objects:
                removed_items.append(
                    {"provider_uuid": bill.provider_id, "billing_period_start": str(bill.billing_period_start)}
                )
                all_providers.add(bill.provider_id)
                all_period_starts.add(str(bill.billing_period_start))

            LOG.info(f"Deleting data for providers {sorted(all_providers)} and periods {sorted(all_period_starts)}")

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
                cascade_delete(all_bill_objects.query.model, all_bill_objects, skip_relations=table_models)

        return removed_items
