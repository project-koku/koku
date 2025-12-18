"""Celery configuration for the Koku project."""
import logging
import os
import time
from datetime import datetime
from datetime import timedelta
from pprint import pprint

from celery import Celery
from celery import Task
from celery.schedules import crontab
from celery.schedules import ParseException
from celery.signals import celeryd_after_setup
from celery.signals import worker_process_init
from django.conf import settings
from kombu.exceptions import OperationalError

from .database import FKViolation
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
        if fk_violation := FKViolation(exc):
            LOG.warning("task failed: %s", fk_violation)
        else:
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


def validate_cron_expression(expression, default="0 * * * *"):
    if len(expression.split(" ", 5)) != 5:
        print(f"Invalid cron expression: {expression}. Falling back to default {default}")
        expression = default
    try:
        crontab(*expression.split(" ", 5))
    except (ValueError, ParseException) as e:
        print(f"Invalid cron expression: {expression}. Falling back to default {default}, Error: {e}")
        expression = default
    return expression


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.settings")

print("starting celery")
# 'app' is the recommended convention from celery docs
# following this for ease of comparison to reference implementation
app = LoggingCelery(
    "koku", log="koku.log:TaskRootLogging", backend=settings.CELERY_RESULTS_URL, broker=settings.CELERY_BROKER_URL
)
app.config_from_object("django.conf:settings", namespace="CELERY")

print("celery autodiscover tasks")

# Specify the number of celery tasks to run before recycling the celery worker.
MAX_CELERY_TASKS_PER_WORKER = ENVIRONMENT.int("MAX_CELERY_TASKS_PER_WORKER", default=10)
app.conf.worker_max_tasks_per_child = MAX_CELERY_TASKS_PER_WORKER

# Timeout threshold for a worker process to startup
WORKER_PROC_ALIVE_TIMEOUT = ENVIRONMENT.int("WORKER_PROC_ALIVE_TIMEOUT", default=4)
app.conf.worker_proc_alive_timeout = WORKER_PROC_ALIVE_TIMEOUT

# Toggle to enable/disable scheduled checks for new reports.
if ENVIRONMENT.bool("SCHEDULE_REPORT_CHECKS", default=False):
    download_fallback = validate_cron_expression("0 * * * *")
    download_task = "masu.celery.tasks.check_report_updates"
    # The schedule to scan for new reports.
    download_expression = ENVIRONMENT.get_value("REPORT_DOWNLOAD_SCHEDULE", default=download_fallback)
    REPORT_DOWNLOAD_SCHEDULE = validate_cron_expression(download_expression, download_fallback)
    report_schedule = crontab(*REPORT_DOWNLOAD_SCHEDULE.split(" ", 5))
    CHECK_REPORT_UPDATES_DEF = {
        "task": download_task,
        "schedule": report_schedule,
        "kwargs": {},
    }
    app.conf.beat_schedule["check-report-updates-batched"] = CHECK_REPORT_UPDATES_DEF

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
status_fallback = validate_cron_expression("0 3 * * *")
status_expression = ENVIRONMENT.get_value("SOURCE_STATUS_SCHEDULE", default=status_fallback)
SOURCE_STATUS_SCHEDULE = validate_cron_expression(status_expression, status_fallback)
source_status_schedule = crontab(*SOURCE_STATUS_SCHEDULE.split(" ", 5))

# task to push source status`
app.conf.beat_schedule["source_status_beat"] = {
    "task": "sources.tasks.source_status_beat",
    "schedule": source_status_schedule,
}

# Beat used to collect Azure disk capacities
app.conf.beat_schedule["scrape_azure_storage_capacities"] = {
    "task": "masu.celery.tasks.scrape_azure_storage_capacities",
    "schedule": crontab(hour=2, minute=0),
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

# Beat used for HCS report finalization
app.conf.beat_schedule["finalize_hcs_reports"] = {
    "task": "hcs.tasks.collect_hcs_report_finalization",
    "schedule": crontab(0, 0, day_of_month="15"),
}

# Specify the frequency for checking delayed summary tasks
DELAYED_TASK_POLLING_MINUTES = ENVIRONMENT.get_value("DELAYED_TASK_POLLING_MINUTES", default="30")
trigger_delayed_tasks_schedule = crontab(minute=f"*/{DELAYED_TASK_POLLING_MINUTES}")
app.conf.beat_schedule["delayed_tasks_trigger"] = {
    "task": "masu.celery.tasks.trigger_delayed_tasks",
    "schedule": trigger_delayed_tasks_schedule,
}


# Celery timeout if broker is unavailable to avoid blocking indefinitely
app.conf.broker_transport_options = {"max_retries": 4, "interval_start": 0, "interval_step": 0.5, "interval_max": 3}

app.autodiscover_tasks()

CELERY_INSPECT = app.control.inspect()


# Print the configuration only in the celery workers
hostname = ENVIRONMENT.get_value("HOSTNAME", default="no-hostname-set")
if "koku-clowder-worker" in hostname:
    print("celery config:")
    pprint(app.conf.changes)
# Print the beat schedules only in the scheduler
if "scheduler" in hostname:
    pprint(app.conf.beat_schedule)


@celeryd_after_setup.connect
def wait_for_migrations(sender, instance, **kwargs):  # pragma: no cover
    """Wait for migrations to complete before completing worker startup."""
    from masu.celery.tasks import collect_queue_metrics

    from .database import check_migrations

    httpd = start_probe_server(WorkerProbeServer)

    # This is a special case because check_migrations() returns three values
    # True means migrations are up-to-date
    while check_migrations() != True:  # noqa
        LOG.warning("Migrations not done. Sleeping")
        time.sleep(5)

    httpd.RequestHandlerClass.ready = True  # Set `ready` to true to indicate migrations are done.
    httpd.RequestHandlerClass._collector = collect_queue_metrics

    if ENVIRONMENT.bool("DEBUG_ATTACH", default=False):
        import debugpy

        debugpy.listen(("0.0.0.0", 5678))
        print("Waiting for debugger attach on port 5678")
        debugpy.wait_for_client()


@worker_process_init.connect
def init_worker(**kwargs):
    from koku.feature_flags import UNLEASH_CLIENT

    LOG.debug("Initializing UNLEASH_CLIENT for celery worker.")
    UNLEASH_CLIENT.initialize_client()


def is_task_currently_running(task_name, task_id, check_args=None):
    """Check if a specific task with optional args is currently running."""
    try:
        active_dict = CELERY_INSPECT.active()
    except OperationalError:
        LOG.warning("Cannot connect to Redis.")
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
