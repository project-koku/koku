#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Configuration loader for Masu application."""
from django.conf import settings

from koku.configurator import CONFIGURATOR
from koku.env import ENVIRONMENT


DEFAULT_ACCOUNT_ACCCESS_TYPE = "db"
DEFAULT_PVC_DIR = "/var/tmp/masu"
DEFAULT_VOLUME_FILE_RETENTION = 60 * 60 * 24
DEFAULT_REPORT_PROCESSING_BATCH_SIZE = 100000
DEFAULT_MASU_DATE_OVERRIDE = None
DEFAULT_MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY = 1
DEFAULT_INITIAL_INGEST_NUM_MONTHS = 3
DEFAULT_INGEST_OVERRIDE = False
DEFAULT_KAFKA_CONNECT = True
DEFAULT_RETRY_SECONDS = 10
DEFAULT_DEL_RECORD_LIMIT = 5000
DEFAULT_MAX_ITERATIONS = 3
DEFAULT_ENABLE_PARQUET_PROCESSING = False


class Config:
    """Configuration for app."""

    DEBUG = ENVIRONMENT.bool("DEVELOPMENT", default=False)

    # Set method for retreiving CUR accounts. 'db' or 'network'
    ACCOUNT_ACCESS_TYPE = ENVIRONMENT.get_value("ACCOUNT_ACCESS_TYPE", default=DEFAULT_ACCOUNT_ACCCESS_TYPE)

    # Data directory for processing incoming data.  This is the OCP PVC mount point.
    PVC_DIR = ENVIRONMENT.get_value("PVC_DIR", default=DEFAULT_PVC_DIR)

    # File retention time for cleaning out the volume (in seconds) # defaults to 1 day
    VOLUME_FILE_RETENTION = ENVIRONMENT.int("VOLUME_FILE_RETENTION", default=DEFAULT_VOLUME_FILE_RETENTION)

    # OCP intermediate report storage
    INSIGHTS_LOCAL_REPORT_DIR = f"{PVC_DIR}/insights_local"

    # Processing intermediate report storage
    TMP_DIR = f"{PVC_DIR}/processing"

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

    # TODO: Remove this if/when reporting model files are owned by masu
    # The decimal precision of our database Numeric columns
    REPORTING_DECIMAL_PRECISION = 9

    # Specify the number of months (bills) to ingest
    INITIAL_INGEST_NUM_MONTHS = ENVIRONMENT.int("INITIAL_INGEST_NUM_MONTHS", default=DEFAULT_INITIAL_INGEST_NUM_MONTHS)

    # Override the initial ingest requirement to allow INITIAL_INGEST_NUM_MONTHS
    INGEST_OVERRIDE = ENVIRONMENT.bool("INITIAL_INGEST_OVERRIDE", default=DEFAULT_INGEST_OVERRIDE)

    # Trino enablement
    TRINO_ENABLED = ENVIRONMENT.bool("ENABLE_PARQUET_PROCESSING", default=DEFAULT_ENABLE_PARQUET_PROCESSING)

    # Insights Kafka
    INSIGHTS_KAFKA_HOST = CONFIGURATOR.get_kafka_broker_host()
    INSIGHTS_KAFKA_PORT = CONFIGURATOR.get_kafka_broker_port()
    INSIGHTS_KAFKA_ADDRESS = f"{INSIGHTS_KAFKA_HOST}:{INSIGHTS_KAFKA_PORT}"
    HCCM_TOPIC = CONFIGURATOR.get_kafka_topic("platform.upload.hccm")
    VALIDATION_TOPIC = CONFIGURATOR.get_kafka_topic("platform.upload.validation")

    # Flag to signal whether or not to connect to upload service
    KAFKA_CONNECT = ENVIRONMENT.bool("KAFKA_CONNECT", default=DEFAULT_KAFKA_CONNECT)

    RETRY_SECONDS = ENVIRONMENT.int("RETRY_SECONDS", default=DEFAULT_RETRY_SECONDS)

    DEL_RECORD_LIMIT = ENVIRONMENT.int("DELETE_CYCLE_RECORD_LIMIT", default=DEFAULT_DEL_RECORD_LIMIT)
    MAX_ITERATIONS = ENVIRONMENT.int("DELETE_CYCLE_MAX_RETRY", default=DEFAULT_MAX_ITERATIONS)
