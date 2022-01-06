"""Celery configuration for the Koku project."""
import logging
import os
import time
from datetime import datetime
from datetime import timedelta

from celery import Celery
from celery import Task
from celery.schedules import crontab
from celery.signals import celeryd_after_setup
from celery.signals import worker_process_init
from celery.signals import worker_process_shutdown
from django.conf import settings
from kombu.exceptions import OperationalError

from koku import sentry  # noqa: F401
from koku.env import ENVIRONMENT
from koku.probe_server import ProbeResponse
from koku.probe_server import ProbeServer
from koku.probe_server import start_probe_server


LOG = logging.getLogger(__name__)


class LogErrorsTask(Task):  # pragma: no cover
    """Log Celery task exceptions."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log exceptions when a celery task fails."""
        LOG.exception("Task failed: %s", exc, exc_info=exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)


class LoggingCelery(Celery):
    """Log Celery task exceptions."""

    def task(self, *args, **kwargs):
        """Set the default base logger for the celery app.

        Let's us avoid typing `base=LogErrorsTask` for every app.task.
        """
        kwargs.setdefault("base", LogErrorsTask)
        return super().task(*args, **kwargs)


class WorkerProbeServer(ProbeServer):  # pragma: no cover
    """HTTP server for liveness/readiness probes."""

    _collector = lambda *args: None  # noqa: E731
    _last_query_time = datetime.min

    @classmethod
    def update_last_query_time(cls, value):
        """Update the last query time."""
        cls._last_query_time = value

    def metrics_check(self):
        """Get the metrics."""
        if datetime.now() - timedelta(minutes=1) > self._last_query_time:
            self.update_last_query_time(datetime.now())
            self._collector()
        super(ProbeServer, self).do_GET()

    def readiness_check(self):
        """Set the readiness check response."""
        status = 424
        msg = "not ready"
        if self.ready:
            # TODO: Could add extra checks here.
            # if not check_kafka_connection():
            #     response = ProbeResponse(status, "kafka connection error")
            #     self._write_response(response)
            #     self.logger.info(response.json)
            #     return
            status = 200
            msg = "ok"
        self._write_response(ProbeResponse(status, msg))


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.settings")

LOG.info("Starting celery.")
# Setup the database for use in Celery
# django.setup()
# LOG.info("Database configured.")

# 'app' is the recommended convention from celery docs
# following this for ease of comparison to reference implementation
app = LoggingCelery(
    "koku", log="koku.log:TaskRootLogging", backend=settings.CELERY_RESULTS_URL, broker=settings.CELERY_BROKER_URL
)
app.config_from_object("django.conf:settings", namespace="CELERY")

LOG.info("Celery autodiscover tasks.")

# Specify the number of celery tasks to run before recycling the celery worker.
MAX_CELERY_TASKS_PER_WORKER = ENVIRONMENT.int("MAX_CELERY_TASKS_PER_WORKER", default=10)
app.conf.worker_max_tasks_per_child = MAX_CELERY_TASKS_PER_WORKER

# Timeout threshold for a worker process to startup
WORKER_PROC_ALIVE_TIMEOUT = ENVIRONMENT.int("WORKER_PROC_ALIVE_TIMEOUT", default=4)
app.conf.worker_proc_alive_timeout = WORKER_PROC_ALIVE_TIMEOUT
LOG.info(f"Celery worker alive timeout = {app.conf.worker_proc_alive_timeout}")

# Toggle to enable/disable scheduled checks for new reports.
if ENVIRONMENT.bool("SCHEDULE_REPORT_CHECKS", default=False):
    # The interval to scan for new reports.
    REPORT_CHECK_INTERVAL = timedelta(minutes=ENVIRONMENT.int("SCHEDULE_CHECK_INTERVAL", default=60))

    CHECK_REPORT_UPDATES_DEF = {
        "task": "masu.celery.tasks.check_report_updates",
        "schedule": REPORT_CHECK_INTERVAL.seconds,
        "args": [],
    }
    app.conf.beat_schedule["check-report-updates"] = CHECK_REPORT_UPDATES_DEF


# Specify the day of the month for removal of expired report data.
REMOVE_EXPIRED_REPORT_DATA_ON_DAY = ENVIRONMENT.int("REMOVE_EXPIRED_REPORT_DATA_ON_DAY", default=1)

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

av_hour = int(VACUUM_HOUR)

if VACUUM_DATA_DAY_OF_WEEK:
    autovacuum_schedule = crontab(day_of_week=VACUUM_DATA_DAY_OF_WEEK, hour=av_hour, minute=int(VACUUM_MINUTE))
else:
    autovacuum_schedule = crontab(hour=av_hour, minute=int(VACUUM_MINUTE))


# This will automatically tune the tables (if needed) based on the number of live tuples
# Based on the latest statistics analysis run
app.conf.beat_schedule["autovacuum-tune-schemas"] = {
    "task": "masu.celery.tasks.autovacuum_tune_schemas",
    "schedule": autovacuum_schedule,
    "args": [],
}

# task to clean up sources with `pending_delete=t`
app.conf.beat_schedule["delete_source_beat"] = {
    "task": "sources.tasks.delete_source_beat",
    "schedule": crontab(minute="0", hour="4"),
}

# Specify the frequency for pushing source status.
SOURCE_STATUS_FREQUENCY_MINUTES = ENVIRONMENT.get_value("SOURCE_STATUS_FREQUENCY_MINUTES", default="30")
source_status_schedule = crontab(minute=f"*/{SOURCE_STATUS_FREQUENCY_MINUTES}")
print(f"Source status schedule: {source_status_schedule}")

# task to push source status`
app.conf.beat_schedule["source_status_beat"] = {
    "task": "sources.tasks.source_status_beat",
    "schedule": source_status_schedule,
}

# Collect prometheus metrics.
app.conf.beat_schedule["db_metrics"] = {"task": "koku.metrics.collect_metrics", "schedule": crontab(hour=1, minute=0)}

# Collect queue metrics.
# app.conf.beat_schedule["queue_metrics"] = {
#     "task": "masu.celery.tasks.collect_queue_metrics",
#     "schedule": crontab(hour="*/1", minute=0),
# }


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

# Beat used to fetch daily rates
app.conf.beat_schedule["get_daily_currency_rates"] = {
    "task": "masu.celery.tasks.get_daily_currency_rates",
    "schedule": crontab(hour=1, minute=0),
}

# Beat used to remove stale tenant data
app.conf.beat_schedule["remove_stale_tenants"] = {
    "task": "masu.processor.tasks.remove_stale_tenants",
    "schedule": crontab(hour=0, minute=0),
}

# Beat used to get Hybrid Committed Spend(HCS) data
hcs_status_schedule = crontab(hour=0, minute=0)
print(f"HCS status schedule: {hcs_status_schedule}")

app.conf.beat_schedule["collect_hcs_report_data"] = {
    "task": "hcs.tasks.collect_hcs_report_data",
    "schedule": hcs_status_schedule,
}

# Celery timeout if broker is unavaiable to avoid blocking indefintely
app.conf.broker_transport_options = {"max_retries": 4, "interval_start": 0, "interval_step": 0.5, "interval_max": 3}

app.autodiscover_tasks()

CELERY_INSPECT = app.control.inspect()


@celeryd_after_setup.connect
def wait_for_migrations(sender, instance, **kwargs):  # pragma: no cover
    """Wait for migrations to complete before completing worker startup."""
    from .database import check_migrations
    from masu.celery.tasks import collect_queue_metrics

    httpd = start_probe_server(WorkerProbeServer)

    # This is a special case because check_migrations() returns three values
    # True means migrations are up-to-date
    while check_migrations() != True:  # noqa
        LOG.warning("Migrations not done. Sleeping")
        time.sleep(5)

    httpd.RequestHandlerClass.ready = True  # Set `ready` to true to indicate migrations are done.
    httpd.RequestHandlerClass._collector = collect_queue_metrics


@worker_process_init.connect
def init_worker(**kwargs):
    from koku.feature_flags import UNLEASH_CLIENT

    LOG.info("Initializing UNLEASH_CLIENT for celery worker.")
    UNLEASH_CLIENT.initialize_client()


@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    from koku.feature_flags import UNLEASH_CLIENT

    LOG.info("Shutting down UNLEASH_CLIENT for celery worker.")
    UNLEASH_CLIENT.destroy()


def is_task_currently_running(task_name, task_id, check_args=None):
    """Check if a specific task with optional args is currently running."""
    try:
        active_dict = CELERY_INSPECT.active()
    except OperationalError:
        LOG.warning("Cannot connect to RabbitMQ.")
        return False
    active_tasks = []
    for task_list in active_dict.values():
        active_tasks.extend(task_list)
    for active_task in active_tasks:
        if active_task.get("id") == task_id:
            # We don't want to count the task doing the is running check
            continue
        if active_task.get("name") == task_name:
            if check_args:
                task_args = set(active_task.get("args", []))
                check_args = set(check_args)
                if task_args >= check_args:
                    # All of our check args are in the task's arg list
                    return True
            else:
                # No check args, we're just checking for the task name
                return True
    # The task isn't running
    return False
