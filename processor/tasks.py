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

from celery import shared_task
from celery.utils.log import get_task_logger

from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file

LOG = get_task_logger(__name__)


@shared_task(name='masu.processor.tasks.get_report_files', queue_name='download')
def get_report_files(customer_name,
                     access_credential,
                     report_source,
                     provider_type,
                     schema_name,
                     report_name=None):
    """
    Task to download a Report.

    Note that report_name will be not optional once Koku can specify
    what report we should download.

    Args:
        customer_name     (String): Name of the customer owning the cost usage report.
        access_credential (String): Credential needed to access cost usage report
                                    in the backend provider.
        report_source     (String): Location of the cost usage report in the backend provider.
        provider_type     (String): Koku defined provider type string.  Example: Amazon = 'AWS'
        report_name       (String): Name of the cost usage report to download.

    Returns:
        files (List) List of filenames with full local path.
               Example: ['/var/tmp/masu/region/aws/catch-clearly.csv',
                         '/var/tmp/masu/base/aws/professor-hour-industry-television.csv']

    """
    reports = _get_report_files(customer_name,
                                access_credential,
                                report_source,
                                provider_type,
                                report_name)

    # initiate chained async task
    for report_dict in reports:
        request = {'schema_name': schema_name,
                   'report_path': report_dict.get('file'),
                   'compression': report_dict.get('compression')}
        process_report_file.delay(**request)


@shared_task(name='masu.processor.tasks.process_report_file', queue_name='process')
def process_report_file(schema_name, report_path, compression):
    """
    Task to process a Report.

    Args:
        schema_name (String) db schema name
        report_path (String) path to downloaded reports
        compression (String) 'PLAIN' or 'GZIP'

    Returns:
        None

    """
    _process_report_file(schema_name, report_path, compression)
