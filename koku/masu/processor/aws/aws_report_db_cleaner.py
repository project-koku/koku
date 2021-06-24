#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes report data from database."""
import logging
from datetime import date
from datetime import datetime

from tenant_schemas.utils import schema_context

from koku.database import cascade_delete
from koku.database import execute_delete_sql
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from reporting.models import PartitionedTable


LOG = logging.getLogger(__name__)


class AWSReportDBCleanerError(Exception):
    """Raise an error during AWS report cleaning."""


class AWSReportDBCleaner:
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
        LOG.info("Calling purge_expired_line_item for aws")
        if not isinstance(expired_date, datetime):
            err = "Parameter expired_date must be a datetime.datetime object."
            raise AWSReportDBCleanerError(err)

        with AWSReportDBAccessor(self._schema) as accessor:
            removed_items = []
            if provider_uuid is not None:
                bill_objects = accessor.get_bill_query_before_date(expired_date, provider_uuid)
            else:
                bill_objects = accessor.get_bill_query_before_date(expired_date)
            with schema_context(self._schema):
                for bill in bill_objects.all():
                    bill_id = bill.id
                    removed_payer_account_id = bill.payer_account_id
                    removed_billing_period_start = bill.billing_period_start

                    if not simulate:
                        lineitem_query = accessor.get_lineitem_query_for_billid(bill_id)
                        del_count = accessor.execute_delete_sql(lineitem_query)
                        LOG.info("Removing %s cost entry line items for bill id %s", del_count, bill_id)

                    LOG.info(
                        "Line item data removed for Account Payer ID: %s with billing period: %s",
                        removed_payer_account_id,
                        removed_billing_period_start,
                    )
                    removed_items.append(
                        {
                            "account_payer_id": removed_payer_account_id,
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
        LOG.info("Calling purge_expired_report_data for aws")

        removed_items = []
        all_account_ids = []
        all_period_start = set()

        with AWSReportDBAccessor(self._schema) as accessor:
            if (expired_date is None and provider_uuid is None) or (  # noqa: W504
                expired_date is not None and provider_uuid is not None
            ):
                err = "This method must be called with either expired_date or provider_uuid"
                raise AWSReportDBCleanerError(err)

            if expired_date is not None:
                return self.purge_expired_report_data_by_date(expired_date, simulate=simulate)

            bill_objects = accessor.get_cost_entry_bills_query_by_provider(provider_uuid)

            with schema_context(self._schema):
                for bill in bill_objects:
                    removed_items.append(
                        {
                            "account_payer_id": bill.payer_account_id,
                            "billing_period_start": str(bill.billing_period_start),
                        }
                    )
                    all_account_ids.append(bill.payer_account_id)
                    all_period_start.add(str(bill.billing_period_start))

                LOG.info(
                    f"Deleting data related to billing account ids {all_account_ids} "
                    f"for billing periods starting {sorted(all_period_start)}"
                )
                if not simulate:
                    cascade_delete(bill_objects.query.model, bill_objects.query.model, bill_objects)

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        paritition_from = str(date(expired_date.year, expired_date.month, 1))
        removed_items = []
        all_account_ids = []
        all_period_start = set()

        with AWSReportDBAccessor(self._schema) as accessor:
            all_bill_objects = accessor.get_bill_query_before_date(expired_date).all()
            for bill in all_bill_objects:
                removed_items.append(
                    {"account_payer_id": bill.payer_account_id, "billing_period_start": str(bill.billing_period_start)}
                )
                all_account_ids.append(bill.payer_account_id)
                all_period_start.add(str(bill.billing_period_start))

            table_names = [
                accessor._table_map["ocp_on_aws_daily_summary"],
                accessor._table_map["ocp_on_aws_project_daily_summary"],
                accessor.line_item_daily_summary_table._meta.db_table,
            ]

        with schema_context(self._schema):
            if not simulate:
                # Will call trigger to detach, truncate, and drop partitions
                del_count = execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=self._schema,
                        partition_of_table_name__in=table_names,
                        partition_parameters__default=False,
                        partition_parameters__from__lte=paritition_from,
                    )
                )
                LOG.info(f"Deleted {del_count} table partitions total for the following tables: {table_names}")

                cascade_delete(all_bill_objects.query.model, all_bill_objects.query.model, all_bill_objects)

            LOG.info(
                f"Deleting data related to billing account ids {all_account_ids} "
                f"for billing periods starting {sorted(all_period_start)}"
            )

        return removed_items
