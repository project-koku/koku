"""Celery configuration for the Koku project."""
import datetime
import logging
import os

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

from . import database
from .env import ENVIRONMENT

LOGGER = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'koku.settings')

LOGGER.info('Starting celery.')
# Setup the database for use in Celery
database.config()
LOGGER.info('Database configured.')

celery = Celery('koku', broker=settings.CELERY_BROKER_URL)
celery.config_from_object('django.conf:settings', namespace='CELERY')

LOGGER.info('Celery autodiscover tasks.')

# Toggle to enable/disable scheduled checks for new reports.
if ENVIRONMENT.bool('SCHEDULE_REPORT_CHECKS', default=False):
    # The interval to scan for new reports.
    REPORT_CHECK_INTERVAL = datetime.timedelta(
        minutes=int(os.getenv('SCHEDULE_CHECK_INTERVAL', '60')))

    check_report_updates_def = {'task': 'masu.celery.tasks.check_report_updates',
                                'schedule': REPORT_CHECK_INTERVAL.seconds,
                                'args': []}
    celery.conf.beat_schedule['check-report-updates'] = check_report_updates_def


# Specify the day of the month for removal of expired report data.
REMOVE_EXPIRED_REPORT_DATA_ON_DAY = int(ENVIRONMENT.get_value('REMOVE_EXPIRED_REPORT_DATA_ON_DAY', default='1'))

# Specify the time of the day for removal of expired report data.
REMOVE_EXPIRED_REPORT_UTC_TIME = ENVIRONMENT.get_value('REMOVE_EXPIRED_REPORT_UTC_TIME', default='00:00')

if REMOVE_EXPIRED_REPORT_DATA_ON_DAY != 0:
    cleaning_day = REMOVE_EXPIRED_REPORT_DATA_ON_DAY
    cleaning_time = REMOVE_EXPIRED_REPORT_UTC_TIME
    hour, minute = cleaning_time.split(':')

    remove_expired_data_def = {'task': 'masu.celery.tasks.remove_expired_data',
                               'schedule': crontab(hour=int(hour),
                                                   minute=int(minute),
                                                   day_of_month=cleaning_day),
                               'args': []}
    celery.conf.beat_schedule['remove-expired-data'] = remove_expired_data_def

celery.autodiscover_tasks()
