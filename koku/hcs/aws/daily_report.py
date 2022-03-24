#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Summary Updater for AWS Parquet files."""
import logging

from django.conf import settings
from tenant_schemas.utils import schema_context

from hcs.database.aws_report_db_accessor import HCSAWSReportDBAccessor
from koku.pg_partition import PartitionHandlerMixin
from masu.external.date_accessor import DateAccessor
from masu.util.common import date_range
from reporting.provider.aws.models import PRESTO_LINE_ITEM_TABLE

LOG = logging.getLogger(__name__)


class AWSReportHCS(PartitionHandlerMixin):
    """Class to write AWS HCS daily report summary data."""

    def __init__(self, schema_name, provider, provider_uuid):
        """Establish parquet summary processor."""
        self._schema_name = schema_name
        self._provider = provider
        self._provider_uuid = provider_uuid
        self._date_accessor = DateAccessor()

    def generate_report(self, start_date, end_date, tracing_id):
        """Generate HCS daily report
        :param start_date (str) The date to start populating the table.
        :param end_date   (str) The date to end on.
        :param tracing_id (uuid) Logging identifier

        :returns (str, str) A start date and end date.

        """
        sql_file = "trino_sql/reporting_aws_hcs_daily_summary.sql"

        with schema_context(self._schema_name):
            self._handle_partitions(self._schema_name, PRESTO_LINE_ITEM_TABLE, start_date, end_date)

        with HCSAWSReportDBAccessor(self._schema_name) as accessor:
            for date in date_range(start_date, end_date, step=settings.TRINO_DATE_STEP):
                accessor.get_hcs_daily_summary(date, self._provider, self._provider_uuid, sql_file, tracing_id)
