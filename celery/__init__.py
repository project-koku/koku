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
"""Celery module."""

from celery import Celery
from celery.schedules import crontab

from masu.config import Config


# pylint: disable=invalid-name, redefined-outer-name
celery = Celery(__name__, broker=Config.CELERY_BROKER_URL)


def update_celery_config(celery, app):
    """Create Celery app object using the Flask app's settings."""
    celery.conf.update(app.config)

    # Define queues used for report processing
    celery.conf.task_routes = {
        'masu.processor.tasks.get_report_files': {'queue': 'download'},
        'masu.processor.tasks.process_report_file': {'queue': 'process'},
        'masu.processor.tasks.remove_expired_data': {'queue': 'remove_expired'},
        'masu.processor.tasks.update_report_tables': {'queue': 'reporting'},
        'masu.celery.tasks.remove_expired_data': {'queue': 'remove_expired'},
    }

    celery.conf.imports = ('masu.processor.tasks', 'masu.celery.tasks')

    # Celery Beat schedule
    if app.config.get('SCHEDULE_REPORT_CHECKS'):
        check_report_updates_def = {'task': 'masu.celery.tasks.check_report_updates',
                                    'schedule': app.config.get('REPORT_CHECK_INTERVAL'),
                                    'args': []}
        celery.conf.beat_schedule['check-report-updates'] = check_report_updates_def

    if app.config.get('REMOVE_EXPIRED_REPORT_DATA_ON_DAY') != 0:
        cleaning_day = app.config.get('REMOVE_EXPIRED_REPORT_DATA_ON_DAY')
        remove_expired_data_def = {'task': 'masu.celery.tasks.remove_expired_data',
                                   'schedule': crontab(day_of_month=cleaning_day),
                                   'args': []}
        celery.conf.beat_schedule['remove-expired-data'] = remove_expired_data_def

    # pylint: disable=too-few-public-methods
    class ContextTask(celery.Task):
        """Celery Task Context."""

        def __call__(self, *args, **kwargs):
            """Call task with context."""
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
