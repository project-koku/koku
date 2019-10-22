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

import logging
import os


LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods,simplifiable-if-expression
class Config:
    """Configuration for app."""

    DEBUG_STRING = os.getenv('MASU_DEBUG', 'False')
    DEBUG = True if (DEBUG_STRING.lower() in ('t', 'true')) else False

    # Database
    DB_ENGINE = os.getenv('DATABASE_ENGINE', 'postgresql')
    DB_NAME = os.getenv('DATABASE_NAME', 'postgres')
    DB_USER = os.getenv('DATABASE_USER', 'postgres')
    DB_PASSWORD = os.getenv('DATABASE_PASSWORD', 'postgres')
    DB_HOST = os.getenv('DATABASE_HOST', 'localhost')
    DB_PORT = os.getenv('DATABASE_PORT', '15432')
    DB_CA_CERT = os.getenv('DATABASE_CA_CERT')

    SQLALCHEMY_DATABASE_URI = \
        f'{DB_ENGINE}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

    # Override for sqlite
    if DB_ENGINE == 'sqlite':
        SQLALCHEMY_DATABASE_URI = f'{DB_ENGINE}:///{DB_NAME}.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_POOL_SIZE = 10

    # Koku Connectivity
    KOKU_HOST = os.getenv('KOKU_HOST_ADDRESS', 'localhost')
    KOKU_PORT = os.getenv('KOKU_PORT', '8000')
    KOKU_ADMIN_USER = os.getenv('SERVICE_ADMIN_USER', 'admin')
    KOKU_ADMIN_PASS = os.getenv('SERVICE_ADMIN_PASSWORD', 'pass')
    KOKU_ACCESS_PROTOCOL = os.getenv('KOKU_ACCESS_PROTOCOL', 'http')

    KOKU_BASE_URL = \
        f'{KOKU_ACCESS_PROTOCOL}://{KOKU_HOST}:{KOKU_PORT}'

    # Set method for retreiving CUR accounts. 'db' or 'network'
    ACCOUNT_ACCESS_TYPE = os.getenv('ACCOUNT_ACCESS_TYPE', 'db')

    # AMQP Message Broker
    RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT = os.getenv('RABBITMQ_PORT', '5672')

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Cloud Watch logging variables.
    # These AWS credential are related to the platform account
    # not cost management account to display all platform logging in
    # a common tooling location for operations.
    CW_AWS_ACCESS_KEY_ID = os.getenv('CW_AWS_ACCESS_KEY_ID')
    CW_AWS_SECRET_ACCESS_KEY = os.getenv('CW_AWS_SECRET_ACCESS_KEY')
    CW_AWS_REGION = os.getenv('CW_AWS_REGION', default='us-east-1')
    CW_LOG_GROUP = os.getenv('CW_LOG_GROUP', default='platform-dev')

    # OpenShift Namespace
    NAMESPACE = os.getenv('NAMESPACE', default='unknown')

    # Data directory for processing incoming data.  This is the OCP PVC mount point.
    PVC_DIR = os.getenv('PVC_DIR', default='/var/tmp/masu')

    # OCP intermediate report storage
    INSIGHTS_LOCAL_REPORT_DIR = f'{PVC_DIR}/insights_local'

    # Processing intermediate report storage
    TMP_DIR = f'{PVC_DIR}/processing'

    # Celery settings
    CELERY_BROKER_URL = f'amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}'
    # CELERY_RESULT_BACKEND = f'amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}'

    REPORT_PROCESSING_BATCH_SIZE = 100000

    AWS_DATETIME_STR_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
    OCP_DATETIME_STR_FORMAT = '%Y-%m-%d %H:%M:%S +0000 UTC'
    AZURE_DATETIME_STR_FORMAT = '%Y-%m-%d'

    # Override the service's current date time time. Format: "%Y-%m-%d %H:%M:%S"
    MASU_DATE_OVERRIDE = os.getenv('MASU_DATE_OVERRIDE')

    # Retention policy for the number of months of report data to keep.
    MASU_RETAIN_NUM_MONTHS = int(os.getenv('MASU_RETAIN_NUM_MONTHS', '3'))

    # pylint: disable=fixme
    # TODO: Remove this if/when reporting model files are owned by masu
    # The decimal precision of our database Numeric columns
    REPORTING_DECIMAL_PRECISION = 9

    # Specify the number of months (bills) to ingest
    INITIAL_INGEST_NUM_MONTHS = int(os.getenv('INITIAL_INGEST_NUM_MONTHS', '2'))

    # Override the initial ingest requirement to allow INITIAL_INGEST_NUM_MONTHS
    INGEST_OVERRIDE = False if os.getenv(
        'INITIAL_INGEST_OVERRIDE', 'False') == 'False' else True

    # Insights Kafka messaging address
    INSIGHTS_KAFKA_HOST = os.getenv('INSIGHTS_KAFKA_HOST', 'localhost')

    # Insights Kafka messaging port
    INSIGHTS_KAFKA_PORT = os.getenv('INSIGHTS_KAFKA_PORT', '29092')

    # Insights Kafka server address
    INSIGHTS_KAFKA_ADDRESS = f'{INSIGHTS_KAFKA_HOST}:{INSIGHTS_KAFKA_PORT}'

    # Maximum amount of time to wait before retrying connections to Kafka
    INSIGHTS_KAFKA_CONN_RETRY_MAX = 300

    # Flag to signal whether or not to connect to upload service
    KAFKA_CONNECT = False if os.getenv(
        'KAFKA_CONNECT', 'False') == 'False' else True
