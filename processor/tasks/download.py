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
"""Processing Orchestrator asynchronous tasks."""

import logging

from masu.external.report_downloader import ReportDownloader

LOG = logging.getLogger(__name__)


def get_report_files(customer_name,
                     access_credential,
                     report_source,
                     provider_type,
                     report_name=None):
    """
    Task to download a Cost Usage Report.

    Note that report_name will be not optional once Koku can specify
    what report we should downlad.

    Args:
        None

    Returns:
        files (List) List of filenames with full local path.
               Example: ['/var/tmp/masu/region/aws/catch-clearly.csv',
                         '/var/tmp/masu/base/aws/professor-hour-industry-television.csv']

    """
    stmt = ('Downloading Report for: '
            'credential: {}'
            'source: {}'
            'customer_name: {}'
            'provider: {}')
    log_statement = stmt.format(access_credential, report_source, customer_name, provider_type)
    LOG.info(log_statement)

    downloader = ReportDownloader(customer_name=customer_name,
                                  access_credential=access_credential,
                                  report_source=report_source,
                                  provider_type=provider_type,
                                  report_name=report_name)

    files = downloader.get_current_report()
    return files
