#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Configuration loader for Masu application."""
from koku.configurator import CONFIGURATOR
from koku.env import ENVIRONMENT


class Config:
    """Configuration for app."""

    DEBUG = ENVIRONMENT.bool("DEVELOPMENT", default=False)

    # Set method for retreiving CUR accounts. 'db' or 'network'
    ACCOUNT_ACCESS_TYPE = ENVIRONMENT.get_value("ACCOUNT_ACCESS_TYPE", default="db")

    # Data directory for processing incoming data.  This is the OCP PVC mount point.
    PVC_DIR = ENVIRONMENT.get_value("PVC_DIR", default="/var/tmp/masu")

    # File retention time for cleaning out the volume (in seconds) # defaults to 1 day
    VOLUME_FILE_RETENTION = ENVIRONMENT.int("VOLUME_FILE_RETENTION", default=(60 * 60 * 24))

    # OCP intermediate report storage
    INSIGHTS_LOCAL_REPORT_DIR = f"{PVC_DIR}/insights_local"

    # Processing intermediate report storage
    TMP_DIR = f"{PVC_DIR}/processing"

    # S3 path root for warehoused data
    WAREHOUSE_PATH = "data"
    CSV_DATA_TYPE = "csv"
    PARQUET_DATA_TYPE = "parquet"

    REPORT_PROCESSING_BATCH_SIZE = ENVIRONMENT.int("REPORT_PROCESSING_BATCH_SIZE", default=100000)

    AWS_DATETIME_STR_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    OCP_DATETIME_STR_FORMAT = "%Y-%m-%d %H:%M:%S +0000 UTC"
    AZURE_DATETIME_STR_FORMAT = "%Y-%m-%d"

    # Override the service's current date time time. Format: "%Y-%m-%d %H:%M:%S"
    MASU_DATE_OVERRIDE = ENVIRONMENT.get_value("DATE_OVERRIDE", default=None)

    # Retention policy for the number of months of report data to keep.
    MASU_RETAIN_NUM_MONTHS = ENVIRONMENT.int("RETAIN_NUM_MONTHS", default=6)
    MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY = ENVIRONMENT.int("RETAIN_NUM_MONTHS", default=1)

    # TODO: Remove this if/when reporting model files are owned by masu
    # The decimal precision of our database Numeric columns
    REPORTING_DECIMAL_PRECISION = 9

    # Specify the number of months (bills) to ingest
    INITIAL_INGEST_NUM_MONTHS = ENVIRONMENT.int("INITIAL_INGEST_NUM_MONTHS", default=3)

    # Override the initial ingest requirement to allow INITIAL_INGEST_NUM_MONTHS
    INGEST_OVERRIDE = ENVIRONMENT.bool("INITIAL_INGEST_OVERRIDE", default=False)

    # Insights Kafka
    INSIGHTS_KAFKA_HOST = CONFIGURATOR.get_kafka_broker_host()
    INSIGHTS_KAFKA_PORT = CONFIGURATOR.get_kafka_broker_port()
    INSIGHTS_KAFKA_ADDRESS = f"{INSIGHTS_KAFKA_HOST}:{INSIGHTS_KAFKA_PORT}"
    HCCM_TOPIC = CONFIGURATOR.get_kafka_topic("platform.upload.hccm")
    VALIDATION_TOPIC = CONFIGURATOR.get_kafka_topic("platform.upload.validation")

    # Flag to signal whether or not to connect to upload service
    KAFKA_CONNECT = ENVIRONMENT.bool("KAFKA_CONNECT", default=True)

    RETRY_SECONDS = ENVIRONMENT.int("RETRY_SECONDS", default=10)

    DEL_RECORD_LIMIT = ENVIRONMENT.int("DELETE_CYCLE_RECORD_LIMIT", default=5000)
    MAX_ITERATIONS = ENVIRONMENT.int("DELETE_CYCLE_MAX_RETRY", default=3)
