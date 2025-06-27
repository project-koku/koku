#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import pkgutil

from api.common import log_json
from api.iam.models import Customer
from api.provider.models import Provider
from hcs.csv_file_handler import CSVFileHandler
from hcs.exceptions import HCSTableNotFoundError
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.provider.aws.models import TRINO_LINE_ITEM_DAILY_TABLE as AWS_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.azure.models import TRINO_LINE_ITEM_DAILY_TABLE as AZURE_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import TRINO_LINE_ITEM_DAILY_TABLE as GCP_TRINO_LINE_ITEM_DAILY_TABLE

LOG = logging.getLogger(__name__)

HCS_TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_AZURE: AZURE_TRINO_LINE_ITEM_DAILY_TABLE,
    Provider.PROVIDER_GCP: GCP_TRINO_LINE_ITEM_DAILY_TABLE,
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
        ctx = {
            "schema": self.schema,
            "provider_type": provider,
            "provider_uuid": provider_uuid,
            "date": date,
            "org_id": self._org_id,
            "ebs_account": self._ebs_acct_num,
        }
        LOG.info(log_json(tracing_id, msg="acquiring marketplace data", context=ctx))

        try:
            sql = pkgutil.get_data("hcs.database", sql_summary_file)
            sql = sql.decode("utf-8")
            table = HCS_TABLE_MAP.get(provider)

            if not self.table_exists_trino(table):
                raise HCSTableNotFoundError(table)

            sql_params = {
                "provider_uuid": str(provider_uuid),
                "year": date.strftime("%Y"),
                "month": date.strftime("%m"),
                "date": date,
                "schema": self.schema,
                "ebs_acct_num": self._ebs_acct_num,
                "org_id": self._org_id,
                "table": table,
            }
            # trino-python-client 0.321.0 released a breaking change to map results to python types by default
            # This altered the timestamp values present in generated CSVs, impacting consumers of these files
            # legacy_primitive_types restores previous functionality of using primitive types
            data, description = self._execute_trino_raw_sql_query_with_description(
                sql, sql_params=sql_params, conn_params={"legacy_primitive_types": True}
            )
            # The format for the description is:
            # [(name, type_code, display_size, internal_size, precision, scale, null_ok)]
            # col[0] grabs the column names from the query results
            cols = [col[0] for col in description]

            if len(data) > 0:
                LOG.info(log_json(tracing_id, msg="data found", context=ctx))
                csv_handler = CSVFileHandler(self.schema, provider, provider_uuid)
                csv_handler.write_csv_to_s3(date, data, cols, finalize, tracing_id)
            else:
                LOG.info(log_json(tracing_id, msg="no data found", context=ctx))

        except FileNotFoundError:
            LOG.error(log_json(tracing_id, msg=f"unable to locate SQL file: {sql_summary_file}"))
