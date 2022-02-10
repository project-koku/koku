"""Custom log-related classes."""
from celery._state import get_current_task
from celery.app.log import Logging
from celery.utils.log import ColorFormatter
from django.core.exceptions import AppRegistryNotReady
from django.db import connection

from .env import ENVIRONMENT


class TaskFormatter(ColorFormatter):
    """
    Formatter for tasks, adding the task name and ids.

    This formatter is strongly inspired by celery.app.log.TaskFormatter.
    """

    def get_connection_pid(self):
        # Putting import here to try to avoid circular import
        from django.apps import apps as koku_apps

        dbpid = "None"
        try:
            if (
                ENVIRONMENT.bool("LOG_DB_PID", False)
                and connection.connection is not None
                and not connection.connection.closed
            ):
                dbpid = f"DBPID_{connection.connection.get_backend_pid()}"
        except AppRegistryNotReady:
            pass

        return {"dbpid": dbpid}

    def get_task_info(self):
        task = get_current_task()

        if task and task.request:
            return {
                "task_id": task.request.id,
                "task_name": task.name,
                "task_root_id": task.request.root_id,
                "task_parent_id": task.request.parent_id,
            }
        else:
            return dict.fromkeys(("task_id", "task_name", "task_root_id", "task_parent_id"), "None")

    def format(self, record):
        """Append task-related values to the record upon format."""
        record.__dict__.update(self.get_connection_pid())
        record.__dict__.update(self.get_task_info())

        return ColorFormatter.format(self, record)


class TaskRootLogging(Logging):
    """Custom Celery application logging setup."""

    def setup_handlers(self, logger, logfile, format, colorize, formatter=TaskFormatter, **kwargs):
        """Ignore the requested formatter and use our custom one."""
        return super().setup_handlers(logger, logfile, format, colorize, TaskFormatter, **kwargs)
