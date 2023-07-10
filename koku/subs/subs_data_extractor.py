#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os
import pkgutil
from functools import cached_property

import boto3
import pandas as pd
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.provider.aws.models import TRINO_LINE_ITEM_TABLE as AWS_TABLE

LOG = logging.getLogger(__name__)

TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_TABLE,
}

SUBS_TRINO_TABLE_NAME = "subs_last_processed_time"


def get_subs_s3_client():  # pragma: no cover
    """Obtain the SUBS s3 session client"""
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    s3_session = boto3.Session(
        aws_access_key_id=settings.S3_SUBS_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SUBS_SECRET,
        region_name=settings.S3_SUBS_REGION,
    )
    return s3_session.client("s3", endpoint_url=settings.S3_ENDPOINT, config=config)


class SUBSDataExtractor(ReportDBAccessorBase):
    def __init__(self, schema, provider_type, provider_uuid, tracing_id, context=None):
        super().__init__(schema)
        self.provider_type = provider_type.removesuffix("-local")
        self.provider_uuid = provider_uuid
        self.tracing_id = tracing_id
        self.table = TABLE_MAP.get(self.provider_type)
        self.s3_client = get_subs_s3_client()
        self.create_subs_table()
        self.context = context

    @cached_property
    def subs_s3_path(self):
        """The S3 path to be used for a SUBS report upload."""
        return f"{self.schema}/{self.provider_type}/source={self.provider_uuid}/date={self.date_helper.today.date()}"

    def create_subs_table(self):
        """Create the table for tracking last processed timestamp for a given month."""
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self.schema}.{SUBS_TRINO_TABLE_NAME}"
            " (last_processed_time timestamp, source varchar, year varchar, month varchar)"
            " WITH(format = 'PARQUET',partitioned_by=ARRAY['source', 'year', 'month'])"
        )
        self._execute_trino_raw_sql_query(sql, log_ref="create_subs_table_if_not_exists")

    def determine_latest_processed_time_for_provider(self, year, month):
        """Determine the latest processed timestamp for a provider for a given month and year."""
        sql = (
            f"SELECT last_processed_time FROM {SUBS_TRINO_TABLE_NAME}"
            f" WHERE source='{self.provider_uuid}' AND year='{year}' AND month='{month}'"
        )
        last_processed_time = self._execute_trino_raw_sql_query(sql, log_ref="determine_last_subs_processed_time")
        if last_processed_time != []:
            return last_processed_time[0][0]
        else:
            return None

    def determine_line_item_count(self, where_clause):
        """Determine the number of records in the table that have not been processed and match the criteria"""
        table_count_sql = f"SELECT count(*) FROM {self.table} {where_clause}"
        count = self._execute_trino_raw_sql_query(table_count_sql, log_ref="determine_subs_processing_count")
        return count[0][0]

    def determine_where_clause(self, latest_processed_time, year, month):
        """Determine the where clause to use when processing subs data"""
        return (
            f"WHERE source='{self.provider_uuid}' AND year='{year}' AND month='{month}' AND"
            " lineitem_productcode = 'AmazonEC2' AND lineitem_lineitemtype = 'Usage' AND"
            " product_vcpu IS NOT NULL AND strpos(resourcetags, 'com_redhat_rhel') > 0 AND"
            f" lineitem_usagestartdate > TIMESTAMP '{latest_processed_time}'"
        )

    def update_latest_processed_time(self, year, month):
        """Update the latest processing time for a provider"""
        delete_old_value_sql = (
            f"DELETE FROM {self.schema}.{SUBS_TRINO_TABLE_NAME}"
            f" WHERE source='{self.provider_uuid}' AND year='{year}' AND month='{month}'"
        )
        self._execute_trino_raw_sql_query(delete_old_value_sql, log_ref="delete_subs_last_processed_time")
        sql = (
            f"INSERT INTO {self.schema}.{SUBS_TRINO_TABLE_NAME} (last_processed_time, source, year, month)"
            " SELECT MAX(lineitem_usagestartdate), '{self.provider_uuid}', '{year}', '{month}' FROM aws_line_items"
            f" WHERE source='{self.provider_uuid}' AND year='{year}' AND month='{month}'"
        )
        self._execute_trino_raw_sql_query(sql, log_ref="insert_subs_last_processed_time")

    def extract_data_to_s3(self, start_date, end_date):
        """Process new subs related line items from reports to S3."""
        LOG.info(log_json(self.tracing_id, msg="beginning subs rhel extraction", context=self.context))
        month = start_date.strftime("%m")
        year = start_date.strftime("%Y")
        latest_processed_time = self.determine_latest_processed_time_for_provider(year, month) or start_date
        where_clause = self.determine_where_clause(latest_processed_time, year, month)
        total_count = self.determine_line_item_count(where_clause)
        LOG.debug(
            log_json(
                self.tracing_id,
                msg=f"identified {total_count} matching records for metered rhel",
                context=self.context,
            )
        )
        upload_keys = []
        filename = f"subs_{self.tracing_id}_"
        sql_file = f"trino_sql/{self.provider_type.lower()}_subs_summary.sql"
        query_sql = pkgutil.get_data("subs", sql_file)
        query_sql = query_sql.decode("utf-8")
        for i, offset in enumerate(range(0, total_count, settings.PARQUET_PROCESSING_BATCH_SIZE)):
            sql_params = {
                "schema": self.schema,
                "provider_uuid": self.provider_uuid,
                "year": year,
                "month": month,
                "time_filter": latest_processed_time,
                "offset": offset,
                "limit": settings.PARQUET_PROCESSING_BATCH_SIZE,
            }
            results, description = self._execute_trino_raw_sql_query_with_description(
                query_sql, sql_params=sql_params, log_ref=f"{self.provider_type.lower()}_subs_summary.sql"
            )

            # The format for the description is:
            # [(name, type_code, display_size, internal_size, precision, scale, null_ok)]
            # col[0] grabs the column names from the query results
            cols = [col[0] for col in description]

            upload_keys.append(self.copy_data_to_subs_s3_bucket(results, cols, f"{filename}{i}.csv"))
        self.update_latest_processed_time(year, month)
        LOG.info(
            log_json(
                self.tracing_id,
                msg=f"{len(upload_keys)} file(s) uploaded to s3 for rhel metering",
                context=self.context,
            )
        )
        return upload_keys

    def copy_data_to_subs_s3_bucket(self, data, cols, filename):
        my_df = pd.DataFrame(data)
        my_df.to_csv(filename, header=cols, index=False)
        with open(filename, "rb") as fin:
            try:
                upload_key = f"{self.subs_s3_path}/{filename}"
                self.s3_client.upload_fileobj(fin, settings.S3_SUBS_BUCKET_NAME, upload_key)
            except (EndpointConnectionError, ClientError) as err:
                msg = f"unable to copy data to {upload_key}, bucket {settings.S3_SUBS_BUCKET_NAME}. Reason: {str(err)}"
                LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context))
                return
        os.remove(filename)
        return upload_key
