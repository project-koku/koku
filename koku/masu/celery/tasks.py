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
"""Asynchronous tasks."""

# pylint: disable=too-many-arguments, too-many-function-args
# disabled module-wide due to current state of task signature.
# we expect this situation to be temporary as we iterate on these details.

from celery.utils.log import get_task_logger

from koku.celery import celery
from masu.external.date_accessor import DateAccessor
from masu.processor.orchestrator import Orchestrator


LOG = get_task_logger(__name__)


@celery.task(name='masu.celery.tasks.check_report_updates')
def check_report_updates():
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator()
    orchestrator.prepare()


@celery.task(name='masu.celery.tasks.remove_expired_data')
def remove_expired_data():
    """Scheduled task to initiate a job to remove expired report data."""
    today = DateAccessor().today()
    LOG.info('Removing expired data at %s', str(today))
    orchestrator = Orchestrator()
    orchestrator.remove_expired_report_data()
