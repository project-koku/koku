#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import pkgutil

from jinjasql import JinjaSql

from api.common import log_json
from api.iam.models import Customer
from api.provider.models import Provider
from hcs.csv_file_handler import CSVFileHandler
from hcs.exceptions import HCSTableNotFoundError
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.aws.models import PRESTO_LINE_ITEM_DAILY_TABLE as AWS_PRESTO_LINE_ITEM_DAILY_TABLE
from reporting.provider.azure.models import PRESTO_LINE_ITEM_DAILY_TABLE as AZURE_PRESTO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import PRESTO_LINE_ITEM_DAILY_TABLE as GCP_PRESTO_LINE_ITEM_DAILY_TABLE

LOG = logging.getLogger(__name__)

HCS_TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_PRESTO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_AZURE: AZURE_PRESTO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_GCP: GCP_PRESTO_LINE_ITEM_DAILY_TABLE,
}


class HCSReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        :param schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        hcs_cust = Customer.objects.filter(schema_name=schema).first()
        self._ebs_acct_num = hcs_cust.account_id
        self._org_id = hcs_cust.org_id
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()

    def get_hcs_daily_summary(self, date, provider, provider_uuid, sql_summary_file, tracing_id, finalize=False):
        """Build HCS daily report.
        :param date             (datetime.date) The date to process
        :param provider         (str)           The provider name
        :param provider_uuid    (uuid)          ID for cost source
        :param sql_summary_file (str)           The sql file used for processing
        :param tracing_id       (id)            Logging identifier
        :param finalize         (bool)          Set True when report is finalized(default=False)

        :returns (None)
        """
        LOG.info(log_json(tracing_id, "acquiring marketplace data..."))
        LOG.info(
            log_json(
                tracing_id,
                f"schema: {self.schema}, provider: {provider}, "
                + f"date: {date}, org_id: {self._org_id}, ebs_num: {self._ebs_acct_num}",
            )
        )

        try:
            sql = pkgutil.get_data("hcs.database", sql_summary_file)
            sql = sql.decode("utf-8")
            table = HCS_TABLE_MAP.get(provider)

            if not self.table_exists_trino(table):
                raise HCSTableNotFoundError(table)

            sql_params = {
                "provider_uuid": provider_uuid,
                "year": date.year,
                "month": date.strftime("%m"),
                "date": date,
                "schema": self.schema,
                "ebs_acct_num": self._ebs_acct_num,
                "org_id": self._org_id,
                "table": table,
            }

            LOG.debug(log_json(tracing_id, f"SQL params: {sql_params}"))

            sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
            data, description = self._execute_trino_raw_sql_query_with_description(sql, sql_params=sql_params)
            # The format for the description is:
            # [(name, type_code, display_size, internal_size, precision, scale, null_ok)]
            # col[0] grabs the column names from the query results
            cols = [col[0] for col in description]

            if len(data) > 0:
                LOG.info(log_json(tracing_id, f"data found for date: {date}"))
                csv_handler = CSVFileHandler(self.schema, provider, provider_uuid)
                csv_handler.write_csv_to_s3(date, data, cols, finalize, tracing_id)
            else:
                LOG.info(
                    log_json(
                        tracing_id,
                        f"no data found for date: {date}, " f"provider: {provider}, provider_uuid: {provider_uuid}",
                    )
                )

        except FileNotFoundError:
            LOG.error(log_json(tracing_id, f"unable to locate SQL file: {sql_summary_file}"))
