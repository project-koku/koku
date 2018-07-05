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
"""Celery task definitions."""

# pylint: disable=unused-argument, fixme, unused-import
# FIXME: temporary module-wide disable until tasks are fully implemented.

from celery.task import periodic_task
from celery.utils.log import get_task_logger

from masu.config import Config
from masu.processor.orchestrator import Orchestrator

LOG = get_task_logger(__name__)


# TODO: Get periodic test to work
@periodic_task(run_every=Config.REPORT_CHECK_INTERVAL)
def check_report_updates():
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator()
    orchestrator.prepare()
