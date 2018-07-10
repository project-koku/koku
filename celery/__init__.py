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


def create_celery(app):
    """Create Celery app object using the Flask app's settings."""
    celery = Celery(
        app.import_name,
        # backend=app.config.get('CELERY_RESULT_BACKEND'),
        broker=app.config.get('CELERY_BROKER_URL')
    )
    celery.conf.update(app.config)

    # Define queues used for report processing
    celery.conf.task_routes = {
        'masu.processor.tasks.get_report_files': {'queue': 'download'},
        'masu.processor.tasks.process_report_file': {'queue': 'process'}
    }

    celery.conf.imports = ('masu.processor.tasks', 'masu.celery.tasks')

    # Celery Beat schedule
    if app.config.get('SCHEDULE_REPORT_CHECKS'):
        celery.conf.beat_schedule = {
            'check-report-updates': {
                'task': 'masu.celery.tasks.check_report_updates',
                'schedule': app.config.get('REPORT_CHECK_INTERVAL'),
                'args': []
            }
        }

    # pylint: disable=too-few-public-methods
    class ContextTask(celery.Task):
        """Celery Task Context."""

        def __call__(self, *args, **kwargs):
            """Call task with context."""
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
