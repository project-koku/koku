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
import calendar
import uuid
from datetime import date

from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger
from dateutil.relativedelta import relativedelta
from django.conf import settings

from api.dataexport.models import DataExportRequest
from api.dataexport.syncer import AwsS3Syncer, SyncedFileInColdStorageError
from koku.celery import app
from masu.celery.export import table_export_settings
from masu.external.date_accessor import DateAccessor
from masu.processor.orchestrator import Orchestrator
from masu.util.upload import query_and_upload_to_s3

LOG = get_task_logger(__name__)


@app.task(name='masu.celery.tasks.check_report_updates')
def check_report_updates():
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator()
    orchestrator.prepare()


@app.task(name='masu.celery.tasks.remove_expired_data')
def remove_expired_data():
    """Scheduled task to initiate a job to remove expired report data."""
    today = DateAccessor().today()
    LOG.info('Removing expired data at %s', str(today))
    orchestrator = Orchestrator()
    orchestrator.remove_expired_report_data()


@app.task(name='masu.celery.tasks.upload_normalized_data', queue_name='upload')
def upload_normalized_data():
    """Scheduled task to export normalized data to s3."""
    log_uuid = str(uuid.uuid4())
    LOG.info('%s Beginning upload_normalized_data', log_uuid)
    curr_date = DateAccessor().today()
    curr_month_range = calendar.monthrange(curr_date.year, curr_date.month)
    curr_month_first_day = date(year=curr_date.year, month=curr_date.month, day=1)
    curr_month_last_day = date(year=curr_date.year, month=curr_date.month, day=curr_month_range[1])

    previous_month = curr_date - relativedelta(months=1)

    prev_month_range = calendar.monthrange(previous_month.year, previous_month.month)
    prev_month_first_day = date(year=previous_month.year, month=previous_month.month, day=1)
    prev_month_last_day = date(year=previous_month.year, month=previous_month.month, day=prev_month_range[1])

    accounts, _ = Orchestrator.get_accounts()

    # Deduplicate schema_name since accounts may have the same schema_name but different providers
    schema_providers = set(
        (account['schema_name'], account['provider_uuid']) for account in accounts
    )
    for schema, provider_uuid in schema_providers:
        LOG.info(
            '%s processing schema %s provider uuid %s', log_uuid, schema, provider_uuid
        )
        for table in table_export_settings:
            # Upload this month's reports
            query_and_upload_to_s3(
                schema,
                provider_uuid,
                table,
                (curr_month_first_day, curr_month_last_day),
            )

            # Upload last month's reports
            query_and_upload_to_s3(
                schema,
                provider_uuid,
                table,
                (prev_month_first_day, prev_month_last_day),
            )
    LOG.info('%s Completed upload_normalized_data', log_uuid)


@app.task(name='masu.celery.tasks.sync_data_to_customer',
          queue_name='customer_data_sync',
          retry_kwargs={'max_retries': 5,
                        'countdown': settings.COLD_STORAGE_RETRIVAL_WAIT_TIME})
def sync_data_to_customer(dump_request_uuid):
    """
    Scheduled task to sync normalized data to our customers S3 bucket.

    If the sync request raises SyncedFileInColdStorageError, this task
    will automatically retry in a set amount of time. This time is to give
    the storage solution time to retrieve a file from cold storage.
    This task will retry 5 times, and then fail.

    """
    dump_request = DataExportRequest.objects.get(uuid=dump_request_uuid)
    dump_request.status = DataExportRequest.PROCESSING
    dump_request.save()

    try:
        syncer = AwsS3Syncer(settings.S3_BUCKET_NAME)
        syncer.sync_bucket(
            dump_request.created_by.customer.schema_name,
            dump_request.bucket_name,
            (dump_request.start_date, dump_request.end_date))
    except ClientError:
        LOG.exception(
            f'Encountered an error while processing DataExportRequest '
            f'{dump_request.uuid}, for {dump_request.created_by}.')
        dump_request.status = DataExportRequest.ERROR
        dump_request.save()
        return
    except SyncedFileInColdStorageError:
        LOG.info(
            f'One of the requested files is currently in cold storage for '
            f'DataExportRequest {dump_request.uuid}. This task will automatically retry.')
        dump_request.status = DataExportRequest.WAITING
        dump_request.save()
        try:
            raise sync_data_to_customer.retry(countdown=10, max_retries=5)
        except MaxRetriesExceededError:
            LOG.exception(
                f'Max retires exceeded for restoring a file in cold storage for '
                f'DataExportRequest {dump_request.uuid}, for {dump_request.created_by}.')
            dump_request.status = DataExportRequest.ERROR
            dump_request.save()
            return
    dump_request.status = DataExportRequest.COMPLETE
    dump_request.save()
