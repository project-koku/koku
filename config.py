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

import datetime
import os


# pylint: disable=too-few-public-methods
class Config(object):
    """Configuration for app."""

    DEBUG_STRING = os.getenv('MASU_DEBUG', 'False')
    DEBUG = True if (DEBUG_STRING.lower() in ('t', 'true')) else False

    # Database
    DB_ENGINE = os.getenv('DATABASE_ENGINE', 'postgresql')
    DB_NAME = os.getenv('DATABASE_NAME', 'postgres')
    DB_USER = os.getenv('DATABASE_USER', 'postgres')
    DB_PASSWORD = os.getenv('DATABASE_PASSWORD', 'postgres')
    DB_HOST = os.getenv('DATABASE_HOST', 'localhost')
    DB_PORT = os.getenv('DATABASE_PORT', 15432)

    # Koku Connectivity
    KOKU_HOST = os.getenv('KOKU_HOST_ADDRESS', 'localhost')
    KOKU_PORT = os.getenv('KOKU_PORT', 8000)
    KOKU_ADMIN_USER = os.getenv('SERVICE_ADMIN_USER', 'admin')
    KOKU_ADMIN_PASS = os.getenv('SERVICE_ADMIN_PASSWORD', 'pass')
    KOKU_ACCESS_PROTOCOL = os.getenv('KOKU_ACCESS_PROTOCOL', 'http')

    KOKU_BASE_URL = \
        f'{KOKU_ACCESS_PROTOCOL}://{KOKU_HOST}:{KOKU_PORT}'

    # Set method for retreiving CUR accounts. 'db' or 'network'
    ACCOUNT_ACCESS_TYPE = os.getenv('ACCOUNT_ACCESS_TYPE', 'db')

    SQLALCHEMY_DATABASE_URI = \
        f'{DB_ENGINE}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

    # Override for sqlite
    if DB_ENGINE == 'sqlite':
        SQLALCHEMY_DATABASE_URI = f'{DB_ENGINE}:///{DB_NAME}.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # AMQP Message Broker
    RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT = os.getenv('RABBITMQ_PORT', '5672')

    SECRET_KEY = os.getenv('MASU_SECRET_KEY')
    if SECRET_KEY is None:
        raise ValueError('No secret key set for Masu application')

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Data directory for processing incoming data
    TMP_DIR = '/var/tmp/masu'

    # Celery settings
    CELERY_BROKER_URL = f'amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}'
    # CELERY_RESULT_BACKEND = f'amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}'

    REPORT_PROCESSING_BATCH_SIZE = 100000

    AWS_DATETIME_STR_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

    # Toggle to enable/disable scheduled checks for new reports.
    SCHEDULE_REPORT_CHECKS = os.getenv('SCHEDULE_REPORT_CHECKS', True)

    # The interval to scan for new reports.
    REPORT_CHECK_INTERVAL = datetime.timedelta(
        minutes=int(os.getenv('SCHEDULE_CHECK_INTERVAL', 60)))

    # Override the service's current date time time. Format: "%Y-%m-%d %H:%M:%S"
    MASU_DATE_OVERRIDE = os.getenv('MASU_DATE_OVERRIDE')

    # Retention policy for the number of months of report data to keep.
    MASU_RETAIN_NUM_MONTHS = int(os.getenv('MASU_RETAIN_NUM_MONTHS', 3))

    # pylint: disable=fixme
    # TODO: Remove this if/when reporting model files are owned by masu
    # The decimal precision of our database Numeric columns
    REPORTING_DECIMAL_PRECISION = 9

    # Specify the day of the month for removal of expired report data.
    REMOVE_EXPIRED_REPORT_DATA_ON_DAY = int(os.getenv('REMOVE_EXPIRED_REPORT_DATA_ON_DAY', 1))
