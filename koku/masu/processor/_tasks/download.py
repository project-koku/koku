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
from masu.database.provider_status_accessor import ProviderStatusCode
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.report_downloader import ReportDownloader
from masu.external.report_downloader import ReportDownloaderError
from masu.processor.worker_cache import WorkerCache
from masu.providers.status import ProviderStatus

LOG = get_task_logger(__name__)


def _get_report_files(
    task, customer_name, authentication, billing_source, provider_type, provider_uuid, report_month, cache_key
):
    """
    Task to download a Report.

    Args:
        task              (Object): Bound celery task.
        customer_name     (String): Name of the customer owning the cost usage report.
        access_credential (String): Credential needed to access cost usage report
                                    in the backend provider.
        report_source     (String): Location of the cost usage report in the backend provider.
        provider_type     (String): Koku defined provider type string.  Example: Amazon = 'AWS'
        provider_uuid     (String): Provider uuid.
        report_month      (DateTime): Month for report to download.
        cache_key         (String): The provider specific task cache value.

    Returns:
        files (List) List of filenames with full local path.
               Example: ['/var/tmp/masu/region/aws/catch-clearly.csv',
                         '/var/tmp/masu/base/aws/professor-hour-industry-television.csv']

    """
    month_string = report_month.strftime("%B %Y")
    log_statement = (
        f"Downloading report for:\n"
        f" schema_name: {customer_name}\n"
        f" provider: {provider_type}\n"
        f" account (provider uuid): {provider_uuid}\n"
        f" report_month: {month_string}"
    )
    LOG.info(log_statement)
    try:
        disk = psutil.disk_usage(Config.PVC_DIR)
        disk_msg = f"Available disk space: {disk.free} bytes ({100 - disk.percent}%)"
    except OSError:
        disk_msg = f"Unable to find available disk space. {Config.PVC_DIR} does not exist"
    LOG.info(disk_msg)

    reports = None
    try:
        downloader = ReportDownloader(
            task=task,
            customer_name=customer_name,
            access_credential=authentication,
            report_source=billing_source,
            provider_type=provider_type,
            provider_uuid=provider_uuid,
            cache_key=cache_key,
            report_name=None,
        )
        reports = downloader.download_report(report_month)
    except (MasuProcessingError, MasuProviderError, ReportDownloaderError) as err:
        worker_stats.REPORT_FILE_DOWNLOAD_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        WorkerCache().remove_task_from_cache(cache_key)
        LOG.error(str(err))
        with ProviderStatus(provider_uuid) as status:
            status.set_error(error=err)
        raise err

    with ProviderStatus(provider_uuid) as status:
        status.set_status(ProviderStatusCode.READY)
    return reports
