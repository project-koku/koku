#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes report data from database."""
import logging
from datetime import date

from django_tenants.utils import schema_context

from api.common import log_json
from koku.database import cascade_delete
from koku.database import execute_delete_sql
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from reporting.models import PartitionedTable
from reporting.provider.aws.models import UI_SUMMARY_TABLES


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

    def purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False):
        """Remove report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        LOG.info(
            log_json(
                msg="calling purge_expired_report_data for AWS",
                schema=self._schema,
                provider_uuid=provider_uuid,
                expired_date=expired_date,
            )
        )

        removed_items = []
        all_account_ids = set()
        all_period_start = set()

        with AWSReportDBAccessor(self._schema) as accessor:
            if (expired_date is None and provider_uuid is None) or (  # noqa: W504
                expired_date is not None and provider_uuid is not None
            ):

                error_msg = log_json(
                    msg="purge_expired_report_data must be called with either expired_date or provider_uuid",
                    provider_type="AWS",
                )
                raise AWSReportDBCleanerError(error_msg)

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
                    all_account_ids.add(bill.payer_account_id)
                    all_period_start.add(str(bill.billing_period_start))

                    LOG.info(
                        log_json(
                            msg="deleting provider billing data for AWS",
                            schema=self._schema,
                            provider_uuid=bill.payer_account_id,
                            start_date=bill.billing_period_start,
                        )
                    )

                if not simulate:
                    cascade_delete(bill_objects.query.model, bill_objects)

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        partition_from = str(date(expired_date.year, expired_date.month, 1))
        removed_items = []
        all_account_ids = set()
        all_period_start = set()

        with AWSReportDBAccessor(self._schema) as accessor:
            all_bill_objects = accessor.get_bill_query_before_date(expired_date).all()
            for bill in all_bill_objects:
                removed_items.append(
                    {"account_payer_id": bill.payer_account_id, "billing_period_start": str(bill.billing_period_start)}
                )
                all_account_ids.add(bill.payer_account_id)
                all_period_start.add(str(bill.billing_period_start))

                LOG.info(
                    log_json(
                        msg="deleting provider billing data for AWS",
                        schema=self._schema,
                        provider_uuid=bill.payer_account_id,
                        start_date=bill.billing_period_start,
                    )
                )

            table_names = [
                accessor._table_map["ocp_on_aws_daily_summary"],
                accessor._table_map["ocp_on_aws_project_daily_summary"],
                accessor.line_item_daily_summary_table._meta.db_table,
                accessor.ocpall_line_item_daily_summary_table._meta.db_table,
                accessor.ocpall_line_item_project_daily_summary_table._meta.db_table,
            ]
            table_names.extend(UI_SUMMARY_TABLES)

        with schema_context(self._schema):
            if not simulate:
                LOG.info(
                    log_json(
                        msg="deleting table partitions",
                        schema=self._schema,
                        tables=table_names,
                        partitions=partition_from,
                    )
                )
                # Will call trigger to detach, truncate, and drop partitions
                del_count = execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=self._schema,
                        partition_of_table_name__in=table_names,
                        partition_parameters__default=False,
                        partition_parameters__from__lte=partition_from,
                    )
                )
                LOG.info(log_json(msg="deleted table partitions", schema=self._schema, records_deleted=del_count))

        return removed_items
