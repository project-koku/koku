#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import pkgutil

from jinjasql import JinjaSql

from api.common import log_json
from hcs.cvs_file_handler import CSVFileHandler
from koku.database import get_model
from koku.database import SQLScriptAtomicExecutorMixin
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.aws.models import AWSCostEntry
from reporting.provider.aws.models import AWSCostEntryLineItem
from reporting.provider.aws.models import AWSCostEntryLineItemDaily
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import PRESTO_LINE_ITEM_TABLE

LOG = logging.getLogger(__name__)


class HCSAWSReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        :param schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()
        self._table_map = AWS_CUR_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return AWSCostEntryLineItemDailySummary

    @property
    def ocpall_line_item_daily_summary_table(self):
        return get_model("OCPAllCostLineItemDailySummaryP")

    @property
    def ocpall_line_item_project_daily_summary_table(self):
        return get_model("OCPAllCostLineItemProjectDailySummaryP")

    @property
    def line_item_table(self):
        return AWSCostEntryLineItem

    @property
    def cost_entry_table(self):
        return AWSCostEntry

    @property
    def line_item_daily_table(self):
        return AWSCostEntryLineItemDaily

    def get_hcs_daily_summary(self, date, provider, provider_uuid, sql_summary_file, tracing_id):
        """Build HCS daily report.
        :param date             (datetime.date) The date to process
        :param provider         (str)           The provider name
        :param provider_uuid    (uuid)          ID for cost source
        :param sql_summary_file (str)           The sql file used for processing
        :param tracing_id       (id)            Logging identifier

        :returns (None)
        """
        LOG.info(log_json(tracing_id, "acquiring AWS market place data..."))
        LOG.info(log_json(tracing_id, f"schema: {self.schema},  provider: {provider}, date: {date}"))

        sql = pkgutil.get_data("hcs.database", sql_summary_file)
        sql = sql.decode("utf-8")

        sql_params = {"date": date, "schema": self.schema, "table": PRESTO_LINE_ITEM_TABLE}

        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        data = self._execute_presto_raw_sql_query(self.schema, sql, bind_params=sql_params)

        if len(data) > 0:
            LOG.info(log_json(tracing_id, f"data found for date: {date}"))
            csv_handler = CSVFileHandler(self.schema, provider, provider_uuid)
            csv_handler.write_csv_to_s3(date, data, tracing_id)
        else:
            LOG.info(log_json(tracing_id, f"data not found for date: {date}"))
