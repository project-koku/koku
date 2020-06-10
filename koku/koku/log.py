"""Custom log-related classes."""
from celery._state import get_current_task
from celery.app.log import Logging
from celery.utils.log import ColorFormatter


class TaskFormatter(ColorFormatter):
    """
    Formatter for tasks, adding the task name and ids.

    This formatter is strongly inspired by celery.app.log.TaskFormatter.
    """

    def format(self, record):
        """Append task-related values to the record upon format."""
        task = get_current_task()

        if task and task.request:
            record.__dict__.update(
                task_id=task.request.id,
                task_name=task.name,
                task_root_id=task.request.root_id,
                task_parent_id=task.request.parent_id,
            )
        else:
            record.__dict__.setdefault("task_name", "None")
            record.__dict__.setdefault("task_id", "None")
            record.__dict__.setdefault("task_root_id", "None")
            record.__dict__.setdefault("task_parent_id", "None")

        return ColorFormatter.format(self, record)


class TaskRootLogging(Logging):
    """Custom Celery application logging setup."""

    def setup_handlers(self, logger, logfile, format, colorize, formatter=TaskFormatter, **kwargs):
        """Ignore the requested formatter and use our custom one."""
        return super().setup_handlers(logger, logfile, format, colorize, TaskFormatter, **kwargs)
