#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Summary Updater for GCP Parquet files."""
import logging

import ciso8601
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from koku.pg_partition import PartitionHandlerMixin
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.util.common import date_range_pair
from reporting.provider.gcp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class GCPReportParquetSummaryUpdater(PartitionHandlerMixin):
    """Class to update GCP report parquet summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish parquet summary processor."""
        self._schema = schema
        self._provider = provider
        self._manifest = manifest

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""

        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()

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

        with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        with GCPReportDBAccessor(self._schema) as accessor:
            with schema_context(self._schema):
                invoice_month = start_date.strftime("%Y%m")
                # Dynamically lookup invoice period date range from trino data
                invoice_dates = accessor.fetch_invoice_month_dates(
                    start_date, end_date, invoice_month, self._provider.uuid
                )
                invoice_start, invoice_end = invoice_dates[0]
                if not invoice_dates or not invoice_dates[0][0]:
                    LOG.info(f"No dates for {invoice_month}. Falling back to original {start_date, end_date}.")
                    invoice_start, invoice_end = start_date, end_date
                bills = accessor.bills_for_provider_uuid(self._provider.uuid, invoice_month=invoice_month)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

                if current_bill_id is None:
                    LOG.info(
                        log_json(
                            msg="no bill was found, skipping summarization",
                            schema=self._schema,
                            provider_uuid=self._provider.uuid,
                            start_date=start_date,
                        )
                    )
                    return start_date, end_date

                for start, end in date_range_pair(invoice_start, invoice_end, step=settings.TRINO_DATE_STEP):
                    LOG.info(
                        log_json(
                            msg="updating GCP report summary tables from parquet",
                            schema=self._schema,
                            provider_uuid=self._provider.uuid,
                            start_date=start,
                            end_date=end,
                            invoice_month=invoice_month,
                            bill_id=current_bill_id,
                        )
                    )
                    filters = {
                        "cost_entry_bill_id": current_bill_id
                    }  # Use cost_entry_bill_id to leverage DB index on DELETE
                    accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
                        self._provider.uuid, start, end, filters
                    )
                    accessor.populate_line_item_daily_summary_table_trino(
                        start, end, self._provider.uuid, current_bill_id, markup_value, invoice_month
                    )
                    accessor.populate_ui_summary_tables(start, end, self._provider.uuid, invoice_month)
                    accessor.populate_gcp_topology_information_tables(
                        self._provider, start_date, end_date, invoice_month
                    )
            accessor.populate_tags_summary_table(bill_ids, start_date, end_date)
            accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, bill_ids)
            for bill in bills:
                if bill.summary_data_creation_datetime is None:
                    bill.summary_data_creation_datetime = timezone.now()
                bill.summary_data_updated_datetime = timezone.now()
                bill.save()

        return start_date, end_date

    def _determine_if_full_summary_update_needed(self, bill):
        """Decide whether to update summary tables for full billing period."""
        summary_creation = bill.summary_data_creation_datetime

        is_done_processing = False
        with ReportManifestDBAccessor() as manifest_accesor:
            is_done_processing = manifest_accesor.manifest_ready_for_summary(self._manifest.id)

        is_new_bill = summary_creation is None

        # Do a full month update if we just finished processing a finalized
        # bill or we just finished processing a bill for the first time
        if is_done_processing and is_new_bill:
            return True

        return False
