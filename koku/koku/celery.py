"""Celery configuration for the Koku project."""
import datetime
import logging
import os
import time

import django
from celery import Celery
from celery import Task
from celery.schedules import crontab
from celery.signals import celeryd_after_setup
from django.conf import settings

from koku import sentry  # noqa: F401
from koku.env import ENVIRONMENT


LOGGER = logging.getLogger(__name__)


class LogErrorsTask(Task):  # pragma: no cover
    """Log Celery task exceptions."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
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
django.setup()
LOGGER.info("Database configured.")

# 'app' is the recommended convention from celery docs
# following this for ease of comparison to reference implementation
app = LoggingCelery(
    "koku", log="koku.log:TaskRootLogging", backend=settings.CELERY_RESULTS_URL, broker=settings.CELERY_BROKER_URL
)
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

# Set the autovacuum-tuning task 1 hour prior to the main vacuum task
av_hour = int(VACUUM_HOUR)
av_hour = 23 if av_hour == 0 else (av_hour - 1)

if VACUUM_DATA_DAY_OF_WEEK:
    schedule = crontab(day_of_week=VACUUM_DATA_DAY_OF_WEEK, hour=int(VACUUM_HOUR), minute=int(VACUUM_MINUTE))
    autovacuum_schedule = crontab(day_of_week=VACUUM_DATA_DAY_OF_WEEK, hour=av_hour, minute=int(VACUUM_MINUTE))
else:
    schedule = crontab(hour=int(VACUUM_HOUR), minute=int(VACUUM_MINUTE))
    autovacuum_schedule = crontab(hour=av_hour, minute=int(VACUUM_MINUTE))

app.conf.beat_schedule["vacuum-schemas"] = {
    "task": "masu.celery.tasks.vacuum_schemas",
    "schedule": schedule,
    "args": [],
}

# This will automatically tune the tables (if needed) based on the number of live tuples
# Based on the latest statistics analysis run
app.conf.beat_schedule["autovacuum-tune-schemas"] = {
    "task": "masu.celery.tasks.autovacuum_tune_schemas",
    "schedule": autovacuum_schedule,
    "args": [],
}


# Collect prometheus metrics.
app.conf.beat_schedule["db_metrics"] = {"task": "koku.metrics.collect_metrics", "schedule": crontab(minute="*/15")}


# optionally specify the weekday and time you would like the clean volume task to run
CLEAN_VOLUME_DAY_OF_WEEK = ENVIRONMENT.get_value("CLEAN_VOLUME_DAY_OF_WEEK", default="sunday")
CLEAN_VOLUME_UTC_TIME = ENVIRONMENT.get_value("CLEAN_VOLUME_UTC_TIME", default="00:00")
CLEAN_HOUR, CLEAN_MINUTE = CLEAN_VOLUME_UTC_TIME.split(":")
# create a task to clean up the volumes - defaults to running every sunday at midnight
if not settings.DEVELOPMENT:
    app.conf.beat_schedule["clean_volume"] = {
        "task": "masu.celery.tasks.clean_volume",
        "schedule": crontab(day_of_week=CLEAN_VOLUME_DAY_OF_WEEK, hour=int(CLEAN_HOUR), minute=int(CLEAN_MINUTE)),
    }


# Beat used to crawl the account hierarchy
app.conf.beat_schedule["crawl_account_hierarchy"] = {
    "task": "masu.celery.tasks.crawl_account_hierarchy",
    "schedule": crontab(hour=0, minute=0),
}

# Beat used to remove stale tenant data
app.conf.beat_schedule["remove_stale_tenants"] = {
    "task": "masu.processor.tasks.remove_stale_tenants",
    "schedule": crontab(hour=0, minute=0),
}

# Celery timeout if broker is unavaiable to avoid blocking indefintely
app.conf.broker_transport_options = {"max_retries": 4, "interval_start": 0, "interval_step": 0.5, "interval_max": 3}

# Specify task routes
app.conf.task_routes = {"sources.tasks.*": {"queue": "sources"}}

app.autodiscover_tasks()

CELERY_INSPECT = app.control.inspect()


@celeryd_after_setup.connect
def wait_for_migrations(sender, instance, **kwargs):  # pragma: no cover
    """Wait for migrations to complete before completing worker startup."""
    from .database import check_migrations

    while not check_migrations():
        LOGGER.warning("Migrations not done. Sleeping")
        time.sleep(5)
