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

from unittest import mock

from celery.utils.log import get_task_logger

from masu import create_app
from masu.celery import create_celery
from masu.processor.exceptions import MasuProcessingError, MasuProviderError

MASU = create_app()
MASU.app_context().push()
CELERY = create_celery(MASU)
LOG = get_task_logger(__name__)


@CELERY.task(autoretry_for=(MasuProviderError,),
             retry_backoff=True)
def check_update(**kwargs):
    """
    Task that checks SNS and/or S3 for updated CUR files.

    A chained Celery task is spawned to download the updated files.

    Args:
        customer (Customer): The customer object from the database.

    Returns:
        results (Boolean): Task success/failure

    Raises:
        MasuProviderError: An error occurred accessing the cloud provider.

    """
    # TODO: 1. look for new data.
    # TODO: 2. when Step 1 is True, add a cache_from_s3() task to the queue.
    return True


@CELERY.task(autoretry_for=(MasuProviderError,),
             retry_backoff=True)
def cache_from_s3(**kwargs):
    """
    Task that downloads CUR from S3.

    The downloaded files are stored in a specified directory for processing.
    A chained Celery task is spawned to process the downloaded files.

    Args:
        customer (Customer): The customer object from the database.
        tmpdir (String): The location to store files downloaded from S3

    Returns:
        results (Boolean): Task success/failure

    Raises:
        MasuProviderError: An error occurred accessing the cloud provider.

    """
    # TODO: 1. download new content (compare E-Tags)
    # TODO: 2. when download completes, add a process_cost_usage_report() task
    # TODO:    to the queue.
    return True


@CELERY.task(autoretry_for=(MasuProcessingError,),
             retry_backoff=True)
def process_cost_usage_report(**kwargs):
    """
    Task that processes CUR files, inserting data into the Koku DB.

    Args:
        customer (Customer): The customer object from the database.
        tmpdir (String): The location to store files downloaded from S3

    Returns:
        results (Boolean): Task success/failure

    Raises:
        MasuProcessingError: An error occurred accessing the cloud provider.

    """
    # TODO: 1. Unzip and process each .csv.gz file in processing directory.
    # TODO: 2. Insert any new data found in Step 1, skipping existing data.
    return True


@CELERY.task(track_started=True)
def test(args):
    """Test task. Used only in testing."""
    LOG.debug(args)
    return mock.Mock(name=__name__, args=args)
