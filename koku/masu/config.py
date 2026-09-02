#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Configuration loader for Masu application."""
import importlib
import os
import tempfile
from tempfile import mkdtemp

from django.conf import settings

from koku.env import ENVIRONMENT


DEFAULT_ACCOUNT_ACCCESS_TYPE = "db"
DEFAULT_TMP_DIR = mkdtemp()

# Modules that bind DATA_DIR at import time; refreshed by configure_worker_data_dir().
_DOWNLOADER_MODULES = (
    "masu.external.downloader.aws.aws_report_downloader",
    "masu.external.downloader.aws_local.aws_local_report_downloader",
    "masu.external.downloader.azure.azure_report_downloader",
    "masu.external.downloader.azure_local.azure_local_report_downloader",
    "masu.external.downloader.gcp.gcp_report_downloader",
    "masu.external.downloader.gcp_local.gcp_local_report_downloader",
)
DEFAULT_REPORT_PROCESSING_BATCH_SIZE = 100000
DEFAULT_MASU_DATE_OVERRIDE = None
DEFAULT_INITIAL_INGEST_NUM_MONTHS = 3
DEFAULT_INGEST_OVERRIDE = False
DEFAULT_KAFKA_CONNECT = True
DEFAULT_RETRY_SECONDS = 10
DEFAULT_KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS = 900
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

    # Emit diagnostics before Kafka's 18-minute max.poll.interval.ms expires.
    # This watchdog is diagnostic-only; it never interrupts message processing.
    KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS = ENVIRONMENT.int(
        "KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS", default=DEFAULT_KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS
    )

    DEL_RECORD_LIMIT = ENVIRONMENT.int("DELETE_CYCLE_RECORD_LIMIT", default=DEFAULT_DEL_RECORD_LIMIT)
    MAX_ITERATIONS = ENVIRONMENT.int("DELETE_CYCLE_MAX_RETRY", default=DEFAULT_MAX_ITERATIONS)


def configure_worker_data_dir(worker_id=None):
    """Assign an isolated data directory for a parallel test worker."""
    suffix = f"worker-{worker_id}" if worker_id is not None else "main"
    data_dir = os.path.join(tempfile.gettempdir(), f"koku-test-{suffix}-{os.getpid()}")
    os.makedirs(data_dir, exist_ok=True)

    Config.DATA_DIR = data_dir
    Config.TMP_DIR = f"{data_dir}/processing"
    Config.INSIGHTS_LOCAL_REPORT_DIR = f"{data_dir}/insights_local"
    os.makedirs(Config.TMP_DIR, exist_ok=True)
    os.makedirs(Config.INSIGHTS_LOCAL_REPORT_DIR, exist_ok=True)

    for module_name in _DOWNLOADER_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, "DATA_DIR"):
            module.DATA_DIR = Config.TMP_DIR

    return data_dir
