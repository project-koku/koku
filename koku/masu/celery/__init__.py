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
"""Celery configuration for the Koku project."""

import logging
import os

import django
from celery import Celery
from celery.signals import after_setup_logger
from masu.config import Config

from masu.util import setup_cloudwatch_logging

LOGGER = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'koku.settings')

LOGGER.info('Starting celery.')
# Django setup is required *before* Celery app can start correctly.
django.setup()
LOGGER.info('Django setup.')

APP = Celery('koku', broker=django.conf.settings.CELERY_BROKER_URL)
APP.config_from_object('django.conf:settings', namespace='CELERY')
LOGGER.info('Celery autodiscover tasks.')
APP.autodiscover_tasks()

# The signal decorator is associated with the
# following method signature, but args and kwargs are not currently utilized.
# Learn more about celery signals here:
# http://docs.celeryproject.org/en/v4.2.0/userguide/signals.html#logging-signals
@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):  # pylint: disable=unused-argument
    """Add logging for celery with optional cloud watch."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    setup_cloudwatch_logging(logger)


def update_celery_config(celery, app):
    """Create Celery app object using the Flask app's settings."""
    celery.conf.update(app.config)

    # Define queues used for report processing
    celery.conf.task_routes = {
        'masu.processor.tasks.get_report_files': {'queue': 'download'},
        'masu.processor.tasks.summarize_reports': {'queue': 'process'},
        'masu.processor.tasks.remove_expired_data': {'queue': 'remove_expired'},
        'masu.processor.tasks.update_report_tables': {'queue': 'reporting'},
        'masu.celery.tasks.remove_expired_data': {'queue': 'remove_expired'},
    }

    celery.conf.imports = ('masu.processor.tasks', 'masu.celery.tasks')
    # Establish a new connection each task
    celery.conf.broker_pool_limit = None
    celery.conf.worker_concurrency = 2
    # Only grab one task at a time
    celery.conf.worker_prefetch_multiplier = 1

    # Celery Beat schedule
    if app.config.get('SCHEDULE_REPORT_CHECKS'):
        check_report_updates_def = {'task': 'masu.celery.tasks.check_report_updates',
                                    'schedule': app.config.get('REPORT_CHECK_INTERVAL'),
                                    'args': []}
        celery.conf.beat_schedule['check-report-updates'] = check_report_updates_def

    if app.config.get('REMOVE_EXPIRED_REPORT_DATA_ON_DAY') != 0:
        cleaning_day = app.config.get('REMOVE_EXPIRED_REPORT_DATA_ON_DAY')
        cleaning_time = app.config.get('REMOVE_EXPIRED_REPORT_UTC_TIME')
        hour, minute = cleaning_time.split(':')

        remove_expired_data_def = {'task': 'masu.celery.tasks.remove_expired_data',
                                   'schedule': crontab(hour=int(hour),
                                                       minute=int(minute),
                                                       day_of_month=cleaning_day),
                                   'args': []}
        celery.conf.beat_schedule['remove-expired-data'] = remove_expired_data_def