"""Celery configuration for the Koku project."""
import datetime
import logging
import os

from celery import Celery
from celery import Task
from celery.schedules import crontab
from django.conf import settings

from . import database
from . import sentry  # pylint: disable=unused-import # noqa: F401
from .env import ENVIRONMENT

# We disable pylint here because we wanted to avoid duplicate code
# in settings and celery config files, therefore we import a single
# file, since we don't actually call anything in it, pylint gets angry.

LOGGER = logging.getLogger(__name__)


# pylint: disable=abstract-method
class LogErrorsTask(Task):  # pragma: no cover
    """Log Celery task exceptions."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # pylint: disable=too-many-arguments
        """Log exceptions when a celery task fails."""
        LOGGER.exception("Task failed: %s", exc, exc_info=exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)


class LoggingCelery(Celery):
    """Log Celery task exceptions."""

    def task(self, *args, **kwargs):
        """Set the default base logger for the celery app.

        Let's us avoid typing `base=LogErrorsTask` for every app.task.
        """
        kwargs.setdefault("base", LogErrorsTask)
        return super().task(*args, **kwargs)


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.settings")

LOGGER.info("Starting celery.")
# Setup the database for use in Celery
database.config()
LOGGER.info("Database configured.")

# 'app' is the recommended convention from celery docs
# following this for ease of comparison to reference implementation
# pylint: disable=invalid-name
app = LoggingCelery("koku", log="koku.log:TaskRootLogging", broker=settings.CELERY_BROKER_URL)
app.config_from_object("django.conf:settings", namespace="CELERY")

LOGGER.info("Celery autodiscover tasks.")

# Toggle to enable/disable scheduled checks for new reports.
if ENVIRONMENT.bool("SCHEDULE_REPORT_CHECKS", default=False):
    # The interval to scan for new reports.
    REPORT_CHECK_INTERVAL = datetime.timedelta(minutes=int(os.getenv("SCHEDULE_CHECK_INTERVAL", "60")))

    CHECK_REPORT_UPDATES_DEF = {
        "task": "masu.celery.tasks.check_report_updates",
        "schedule": REPORT_CHECK_INTERVAL.seconds,
        "args": [],
    }
    app.conf.beat_schedule["check-report-updates"] = CHECK_REPORT_UPDATES_DEF


# Specify the day of the month for removal of expired report data.
REMOVE_EXPIRED_REPORT_DATA_ON_DAY = int(ENVIRONMENT.get_value("REMOVE_EXPIRED_REPORT_DATA_ON_DAY", default="1"))

# Specify the time of the day for removal of expired report data.
REMOVE_EXPIRED_REPORT_UTC_TIME = ENVIRONMENT.get_value("REMOVE_EXPIRED_REPORT_UTC_TIME", default="00:00")

if REMOVE_EXPIRED_REPORT_DATA_ON_DAY != 0:
    CLEANING_DAY = REMOVE_EXPIRED_REPORT_DATA_ON_DAY
    CLEANING_TIME = REMOVE_EXPIRED_REPORT_UTC_TIME
    HOUR, MINUTE = CLEANING_TIME.split(":")

    REMOVE_EXPIRED_DATA_DEF = {
        "task": "masu.celery.tasks.remove_expired_data",
        "schedule": crontab(hour=int(HOUR), minute=int(MINUTE), day_of_month=CLEANING_DAY),
        "args": [],
    }
    app.conf.beat_schedule["remove-expired-data"] = REMOVE_EXPIRED_DATA_DEF


# Specify the day of the month for removal of expired report data.
VACUUM_DATA_DAY_OF_WEEK = ENVIRONMENT.get_value("VACUUM_DATA_DAY_OF_WEEK", default=None)

# Specify the time of the day for removal of expired report data.
VACUUM_DATA_UTC_TIME = ENVIRONMENT.get_value("VACUUM_DATA_UTC_TIME", default="00:00")
VACUUM_HOUR, VACUUM_MINUTE = VACUUM_DATA_UTC_TIME.split(":")

if VACUUM_DATA_DAY_OF_WEEK:
    schedule = crontab(day_of_week=VACUUM_DATA_DAY_OF_WEEK, hour=int(VACUUM_HOUR), minute=int(VACUUM_MINUTE))
else:
    schedule = crontab(hour=int(VACUUM_HOUR), minute=int(VACUUM_MINUTE))

app.conf.beat_schedule["vacuum-schemas"] = {
    "task": "masu.celery.tasks.vacuum_schemas",
    "schedule": schedule,
    "args": [],
}

# Collect prometheus metrics.
app.conf.beat_schedule["db_metrics"] = {"task": "koku.metrics.collect_metrics", "schedule": crontab(minute="*/15")}

# Toggle to enable/disable S3 archiving of account data.
if ENVIRONMENT.bool("ENABLE_S3_ARCHIVING", default=True):
    app.conf.beat_schedule["daily_upload_normalized_reports_to_s3"] = {
        "task": "masu.celery.tasks.upload_normalized_data",
        "schedule": int(os.getenv("UPLOAD_NORMALIZED_DATA_INTERVAL", "86400")),
    }

# Celery timeout if broker is unavaiable to avoid blocking indefintely
app.conf.broker_transport_options = {"max_retries": 4, "interval_start": 0, "interval_step": 0.5, "interval_max": 3}

app.autodiscover_tasks()
