#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Configuration loader for Masu application."""
from tempfile import mkdtemp

from django.conf import settings

from koku.env import ENVIRONMENT


DEFAULT_ACCOUNT_ACCCESS_TYPE = "db"
DEFAULT_TMP_DIR = mkdtemp()
DEFAULT_REPORT_PROCESSING_BATCH_SIZE = 100000
DEFAULT_MASU_DATE_OVERRIDE = None
DEFAULT_MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY = 1
DEFAULT_INITIAL_INGEST_NUM_MONTHS = 3
DEFAULT_INGEST_OVERRIDE = False
DEFAULT_KAFKA_CONNECT = True
DEFAULT_RETRY_SECONDS = 10
DEFAULT_DEL_RECORD_LIMIT = 5000
DEFAULT_MAX_ITERATIONS = 3
DEFAULT_ENABLED_TAG_LIMIT = 200
DEFAULT_ROS_URL_EXPIRATION = 172800


class Config:
    """Configuration for app."""

    DEBUG = ENVIRONMENT.bool("DEVELOPMENT", default=False)

    # Set method for retreiving CUR accounts. 'db' or 'network'
    ACCOUNT_ACCESS_TYPE = ENVIRONMENT.get_value("ACCOUNT_ACCESS_TYPE", default=DEFAULT_ACCOUNT_ACCCESS_TYPE)

    # Data directory for processing incoming data
    DATA_DIR = ENVIRONMENT.get_value("DATA_DIR", default=DEFAULT_TMP_DIR)

    # OCP intermediate report storage
    INSIGHTS_LOCAL_REPORT_DIR = f"{DATA_DIR}/insights_local"

    # Processing intermediate report storage
    TMP_DIR = f"{DATA_DIR}/processing"

    # S3 path root for warehoused data
    WAREHOUSE_PATH = "data"
    CSV_DATA_TYPE = "csv"
    PARQUET_DATA_TYPE = "parquet"

    REPORT_PROCESSING_BATCH_SIZE = ENVIRONMENT.int(
        "REPORT_PROCESSING_BATCH_SIZE", default=DEFAULT_REPORT_PROCESSING_BATCH_SIZE
    )

    AWS_DATETIME_STR_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    OCP_DATETIME_STR_FORMAT = "%Y-%m-%d %H:%M:%S +0000 UTC"
    AZURE_DATETIME_STR_FORMAT = "%Y-%m-%d"

    # Override the service's current date time time. Format: "%Y-%m-%d %H:%M:%S"
    MASU_DATE_OVERRIDE = ENVIRONMENT.get_value("DATE_OVERRIDE", default=DEFAULT_MASU_DATE_OVERRIDE)

    # Retention policy for the number of months of report data to keep.
    MASU_RETAIN_NUM_MONTHS = settings.RETAIN_NUM_MONTHS
    MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY = ENVIRONMENT.int(
        "RETAIN_NUM_MONTHS", default=DEFAULT_MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY
    )

    # Specify the number of months (bills) to ingest
    INITIAL_INGEST_NUM_MONTHS = ENVIRONMENT.int("INITIAL_INGEST_NUM_MONTHS", default=DEFAULT_INITIAL_INGEST_NUM_MONTHS)

    # Override the initial ingest requirement to allow INITIAL_INGEST_NUM_MONTHS
    INGEST_OVERRIDE = ENVIRONMENT.bool("INITIAL_INGEST_OVERRIDE", default=DEFAULT_INGEST_OVERRIDE)

    # Limit the number of enabled tags:
    ENABLED_TAG_LIMIT = ENVIRONMENT.int("TAG_ENABLED_LIMIT", default=DEFAULT_ENABLED_TAG_LIMIT)

    # Set ROS presigned URL expiration:
    ROS_URL_EXPIRATION = ENVIRONMENT.int("ROS_URL_EXPIRATION", default=DEFAULT_ROS_URL_EXPIRATION)

    # Flag to signal whether or not to connect to upload service
    KAFKA_CONNECT = ENVIRONMENT.bool("KAFKA_CONNECT", default=DEFAULT_KAFKA_CONNECT)

    RETRY_SECONDS = ENVIRONMENT.int("RETRY_SECONDS", default=DEFAULT_RETRY_SECONDS)

    DEL_RECORD_LIMIT = ENVIRONMENT.int("DELETE_CYCLE_RECORD_LIMIT", default=DEFAULT_DEL_RECORD_LIMIT)
    MAX_ITERATIONS = ENVIRONMENT.int("DELETE_CYCLE_MAX_RETRY", default=DEFAULT_MAX_ITERATIONS)
