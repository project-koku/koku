#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import logging

import psutil

import masu.prometheus_stats as worker_stats
from api.common import log_json
from masu.config import Config
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.report_downloader import ReportDownloader
from masu.external.report_downloader import ReportDownloaderError
from masu.processor.worker_cache import WorkerCache

LOG = logging.getLogger(__name__)


# disabled until the program flow stabilizes a bit more
# pylint: disable=too-many-arguments,too-many-locals
def _get_report_files(
    request_id,
    customer_name,
    authentication,
    billing_source,
    provider_type,
    provider_uuid,
    report_month,
    cache_key,
    report_context,
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
    context = {"account": customer_name[4:], "provider_uuid": provider_uuid}
    month_string = report_month.strftime("%B %Y")
    report_context["date"] = report_month
    log_statement = (
        f"Downloading report for: "
        f" schema_name: {customer_name} "
        f" provider: {provider_type} "
        f" account (provider uuid): {provider_uuid} "
        f" report_month: {month_string}"
    )
    LOG.info(log_json(request_id, log_statement, context))
    try:
        disk = psutil.disk_usage(Config.PVC_DIR)
        disk_msg = f"Available disk space: {disk.free} bytes ({100 - disk.percent}%)"
    except OSError:
        disk_msg = f"Unable to find available disk space. {Config.PVC_DIR} does not exist"
    LOG.debug(log_json(request_id, disk_msg, context))

    report = None
    try:
        downloader = ReportDownloader(
            customer_name=customer_name,
            credentials=authentication,
            data_source=billing_source,
            provider_type=provider_type,
            provider_uuid=provider_uuid,
            report_name=None,
            account=customer_name[4:],
            request_id=request_id,
        )
        report = downloader.download_report(report_context)
    except (MasuProcessingError, MasuProviderError, ReportDownloaderError) as err:
        worker_stats.REPORT_FILE_DOWNLOAD_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        WorkerCache().remove_task_from_cache(cache_key)
        LOG.error(log_json(request_id, str(err), context))
        raise err

    return report
