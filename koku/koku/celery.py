"""Celery configuration for the Koku project."""
import datetime
import logging
import os

from celery import Celery, Task
from celery.schedules import crontab
from django.conf import settings

from . import database
# We disable pylint here because we wanted to avoid duplicate code
# in settings and celery config files, therefore we import a single
# file, since we don't actually call anything in it, pylint gets angry.
from . import sentry  # pylint: disable=unused-import # noqa: F401
from .env import ENVIRONMENT

LOGGER = logging.getLogger(__name__)

class LogErrorsTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        LOGGER.exception('Task failed: %s' % exc, exc_info=exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)


class LoggingCelery(Celery):
    def task(self, *args, **kwargs):
        kwargs.setdefault('base', LogErrorsTask)
        return super().task(*args, **kwargs)


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'koku.settings')

LOGGER.info('Starting celery.')
# Setup the database for use in Celery
database.config()
LOGGER.info('Database configured.')

# 'app' is the recommended convention from celery docs
# following this for ease of comparison to reference implementation
# pylint: disable=invalid-name
app = LoggingCelery('koku', broker=settings.CELERY_BROKER_URL)
app.config_from_object('django.conf:settings', namespace='CELERY')

LOGGER.info('Celery autodiscover tasks.')

# Toggle to enable/disable scheduled checks for new reports.
if ENVIRONMENT.bool('SCHEDULE_REPORT_CHECKS', default=False):
    # The interval to scan for new reports.
    REPORT_CHECK_INTERVAL = datetime.timedelta(
        minutes=int(os.getenv('SCHEDULE_CHECK_INTERVAL', '60')))

    CHECK_REPORT_UPDATES_DEF = {'task': 'masu.celery.tasks.check_report_updates',
                                'schedule': REPORT_CHECK_INTERVAL.seconds,
                                'args': []}
    app.conf.beat_schedule['check-report-updates'] = CHECK_REPORT_UPDATES_DEF


# Specify the day of the month for removal of expired report data.
REMOVE_EXPIRED_REPORT_DATA_ON_DAY = int(ENVIRONMENT.get_value('REMOVE_EXPIRED_REPORT_DATA_ON_DAY',
                                                              default='1'))

# Specify the time of the day for removal of expired report data.
REMOVE_EXPIRED_REPORT_UTC_TIME = ENVIRONMENT.get_value('REMOVE_EXPIRED_REPORT_UTC_TIME',
                                                       default='00:00')

if REMOVE_EXPIRED_REPORT_DATA_ON_DAY != 0:
    CLEANING_DAY = REMOVE_EXPIRED_REPORT_DATA_ON_DAY
    CLEANING_TIME = REMOVE_EXPIRED_REPORT_UTC_TIME
    HOUR, MINUTE = CLEANING_TIME.split(':')

    REMOVE_EXPIRED_DATA_DEF = {'task': 'masu.celery.tasks.remove_expired_data',
                               'schedule': crontab(hour=int(HOUR),
                                                   minute=int(MINUTE),
                                                   day_of_month=CLEANING_DAY),
                               'args': []}
    app.conf.beat_schedule['remove-expired-data'] = REMOVE_EXPIRED_DATA_DEF

app.conf.beat_schedule['daily_upload_normalized_reports_to_s3'] = {
    'task': 'masu.celery.tasks.upload_normalized_data',
    'schedule': int(os.getenv('UPLOAD_NORMALIZED_DATA_INTERVAL', '86400'))
}

app.autodiscover_tasks()
