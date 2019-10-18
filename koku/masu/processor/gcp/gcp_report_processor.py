"""Processor for GCP Cost Usage Reports."""
import logging
from collections import OrderedDict
from datetime import datetime

import pandas
import pytz
from dateutil import parser
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.config import Config
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util.azure import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill, GCPCostEntryLineItemDaily, GCPProject


LOG = logging.getLogger(__name__)


class ProcessedGCPReport:
    """Cost usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.line_items = []

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.line_items = []


class GCPReportProcessor(ReportProcessorBase):
    """Cost Usage Report processor."""

    # pylint:disable=too-many-arguments
    def __init__(self, schema_name, report_path, compression, provider_id, manifest_id=None):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider_id=provider_id,
            processed_report=ProcessedGCPReport()
        )

        self.provider = Provider.objects.get(id=self._provider_id)

        self.table_name = GCPCostEntryLineItemDaily()

        self.manifest_id = manifest_id
        self._report_name = report_path
        self._datetime_format = Config.AZURE_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        self._schema_name = schema_name

        # Gather database accessors
        with ReportingCommonDBAccessor() as report_common_db:
            self.column_map = report_common_db.column_map

        LOG.info('Initialized report processor for file: %s and schema: %s',
                 report_path, self._schema_name)

    def _get_or_create_cost_entry_bill(self, row):
        """Get or Create a GCP cost entry bill object.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.

        Returns:
             (reporting.provider.gcp.models.GCPCostEntryBill) A GCP Bill instance.

        """
        data = self._get_data_for_table(row, GCPCostEntryLineItemDaily._meta.db_table)

        report_date_range = utils.month_date_range(parser.parse(data['start_time']))
        start_date, end_date = report_date_range.split('-')

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        data['billing_period_start'] = datetime.strftime(start_date_utc, '%Y-%m-%d %H:%M%z')
        data['billing_period_end'] = datetime.strftime(end_date_utc, '%Y-%m-%d %H:%M%z')

        bill, created = GCPCostEntryBill.objects.get_or_create(
            billing_period_start=data['billing_period_start'],
            provider=self.provider,
            billing_period_end=data['billing_period_end']
        )
        return bill

    def _get_or_create_gcp_project(self, row):
        """Get or Create a GCPProject.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.

        Returns:
             (reporting.provider.gcp.models.GCPProject) A GCP Project instance with project_id matching row_id.

        """
        data = self._get_data_for_table(row, GCPProject._meta.db_table)

        project, created = GCPProject.objects.get_or_create(
            account_id=data['account_id'],
            project_id=data['project_id'],
            defaults={
                'project_name': data['project_name'],
                'project_number': data['project_number'],
                'project_labels': data['project_labels']
            }
        )
        return project

    def _create_cost_entry_line_item(self, row, bill, project):
        """Create a cost entry line item object.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row
            bill (reporting.provider.gcp.models.GCPCostEntryBill): A monthly GCPCostEntryBill
            project (reporting.provider.gcp.models.GCPProject): A GCP Project

        """
        data = self._get_data_for_table(row, GCPCostEntryLineItemDaily._meta.db_table)
        line_item = GCPCostEntryLineItemDaily(
            line_item_type=data['line_item_type'],
            cost_entry_bill=bill,
            project=project,
            measurement_type=data['measurement_type'],
            consumption=data['consumption'],
            unit=data['unit'],
            cost=data['cost'],
            currency=data['currency'],
            description=data['description'],
            start_time=data['start_time'],
            end_time=data['end_time'],
        )
        self.processed_report.line_items.append(line_item)

    def process(self):
        """Process GCP billing file."""
        row_count = 0
        with schema_context(self._schema_name):

            report_csv = pandas.read_csv(self._report_path, chunksize=self._batch_size,
                                         compression='infer')
            for chunk in report_csv:
                report_groups = chunk.groupby(by=['Start Time', 'Project ID'])
                for group, rows in report_groups:
                    first_row = OrderedDict(zip(rows.columns.tolist(), rows.iloc[0].tolist()))
                    bill = self._get_or_create_cost_entry_bill(first_row)
                    project = self._get_or_create_gcp_project(first_row)

                    for row in rows.values:
                        processed_row = OrderedDict(zip(rows.columns.tolist(), row.tolist()))
                        self._create_cost_entry_line_item(processed_row, bill, project)

                GCPCostEntryLineItemDaily.objects.bulk_create(
                    self.processed_report.line_items, ignore_conflicts=True
                )
                LOG.info('Saving report rows %d to %d for %s', row_count,
                         row_count + len(self.processed_report.line_items),
                         self._report_name)
                row_count += len(self.processed_report.line_items)
                self.processed_report.remove_processed_rows()

            LOG.info('Completed report processing for file: %s and schema: %s',
                     self._report_name, self._schema_name)
