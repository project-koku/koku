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

import psutil
from celery.utils.log import get_task_logger

import masu.prometheus_stats as worker_stats
from masu.config import Config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.provider_status_accessor import ProviderStatusCode
from masu.exceptions import MasuProcessingError, MasuProviderError
from masu.external.report_downloader import ReportDownloader, ReportDownloaderError
from masu.providers.status import ProviderStatus

LOG = get_task_logger(__name__)


# disabled until the program flow stabilizes a bit more
# pylint: disable=too-many-arguments,too-many-locals
def _get_report_files(customer_name,
                      authentication,
                      billing_source,
                      provider_type,
                      provider_uuid,
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
        provider_uuid     (String): Provider uuid.
        report_name       (String): Name of the cost usage report to download.

    Returns:
        files (List) List of filenames with full local path.
               Example: ['/var/tmp/masu/region/aws/catch-clearly.csv',
                         '/var/tmp/masu/base/aws/professor-hour-industry-television.csv']

    """
    with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
        reports_processed = provider_accessor.get_setup_complete()
        provider_id = provider_accessor.get_provider().id

    if Config.INGEST_OVERRIDE or not reports_processed:
        number_of_months = Config.INITIAL_INGEST_NUM_MONTHS
    else:
        number_of_months = 2

    stmt = ('Downloading report for'
            ' credential: {},'
            ' source: {},'
            ' customer_name: {},'
            ' provider: {},'
            ' number_of_months: {}')
    log_statement = stmt.format(str(authentication),
                                str(billing_source),
                                customer_name,
                                provider_type,
                                number_of_months)
    LOG.info(log_statement)
    try:
        disk = psutil.disk_usage(Config.PVC_DIR)
        disk_msg = 'Available disk space: {} bytes ({}%)'.format(disk.free, 100 - disk.percent)
    except OSError:
        disk_msg = 'Unable to find available disk space. {} does not exist'.format(Config.PVC_DIR)
    LOG.info(disk_msg)

    reports = None
    try:
        downloader = ReportDownloader(customer_name=customer_name,
                                      access_credential=authentication,
                                      report_source=billing_source,
                                      provider_type=provider_type,
                                      provider_id=provider_id,
                                      report_name=report_name)
        reports = downloader.get_reports(number_of_months)
    except (MasuProcessingError, MasuProviderError, ReportDownloaderError) as err:
        worker_stats.REPORT_FILE_DOWNLOAD_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        LOG.error(str(err))
        with ProviderStatus(provider_uuid) as status:
            status.set_error(error=err)
        raise err

    with ProviderStatus(provider_uuid) as status:
        status.set_status(ProviderStatusCode.READY)
    return reports
