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

from celery.utils.log import get_task_logger

from masu.exceptions import MasuProcessingError, MasuProviderError
from masu.external.report_downloader import ReportDownloader, ReportDownloaderError

LOG = get_task_logger(__name__)


# disabled until the program flow stabilizes a bit more
# pylint: disable=too-many-arguments
def _get_report_files(customer_name,
                      authentication,
                      billing_source,
                      provider_type,
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
    stmt = ('Downloading report for'
            ' credential: {},'
            ' source: {},'
            ' customer_name: {},'
            ' provider: {}')
    log_statement = stmt.format(authentication,
                                billing_source,
                                customer_name,
                                provider_type)
    LOG.info(log_statement)

    try:
        downloader = ReportDownloader(customer_name=customer_name,
                                      access_credential=authentication,
                                      report_source=billing_source,
                                      provider_type=provider_type,
                                      report_name=report_name)
        return downloader.get_current_report()
    except (MasuProcessingError, MasuProviderError, ReportDownloaderError) as err:
        LOG.error(str(err))
        return []
