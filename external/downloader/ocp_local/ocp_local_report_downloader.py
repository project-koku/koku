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
"""OCP Local Report Downloader."""

# pylint: skip-file
# Having trouble disabling the lint warning for duplicate-code (OCPReportDownloader..)
# Disabling pylint on this file since OCPLocalReportDownloader is a DEBUG feature.

import hashlib
import logging
import os
import shutil

from masu.config import Config
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.ocp import common as utils

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

LOG = logging.getLogger(__name__)


class OCPLocalReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """OCP-local Cost and Usage Report Downloader."""

    def __init__(self, customer_name, auth_credential, bucket, report_name=None, **kwargs):
        """
        Initializer.

        Args:
            customer_name    (String) Name of the customer
            auth_credential  (String) OpenShift cluster ID
            report_name      (String) Name of the Cost Usage Report to download (optional)
            bucket           (String) Name of the S3 bucket containing the CUR

        """
        super().__init__(**kwargs)

        LOG.debug('Connecting to OCP-local service provider...')

        self.customer_name = customer_name.replace(' ', '_')
        self.report_name = report_name
        self.cluster_id = auth_credential
        self.provider_id = None
        if 'provider_id' in kwargs:
            self.provider_id = kwargs['provider_id']

    def get_report_for(self, date_time):
        """
        Get OCP usage report files cooresponding to a date.

        Args:
            date_time (DateTime): Start date of the usage report.

        Returns:
            ([]) List of file paths for a particular report.

        """
        dates = utils.month_date_range(date_time)
        LOG.debug('Looking for cluster %s report for date %s', self.cluster_id, str(dates))
        directory = '{}/{}/{}'.format(REPORTS_DIR, self.cluster_id, dates)

        reports = []
        try:
            for file in os.listdir(directory):
                if file.endswith('.csv'):
                    report_full_path = os.path.join(directory, file)
                    LOG.info('Found file %s', report_full_path)
                    reports.append(report_full_path)
        except OSError as error:
            LOG.error('Unable to get report. Error: %s', str(error))
        return reports

    def download_file(self, key, stored_etag=None):
        """
        Download an OCP usage file.

        Args:
            key (str): The OCP file name.

        Returns:
            (String): The path and file name of the saved file

        """
        local_filename = utils.get_local_file_name(key)

        directory_path = f'{DATA_DIR}/{self.customer_name}/ocp-local/{self.cluster_id}'
        full_file_path = f'{directory_path}/{local_filename}'

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        etag_hasher = hashlib.new('ripemd160')
        etag_hasher.update(bytes(local_filename, 'utf-8'))
        ocp_etag = etag_hasher.hexdigest()

        if ocp_etag != stored_etag or not os.path.isfile(full_file_path):
            LOG.info('Downloading %s to %s', key, full_file_path)
            shutil.copy2(key, full_file_path)
        return full_file_path, ocp_etag

    def download_report(self, date_time):
        """
        Download CUR for a given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ([{}]) List of dictionaries containing file path and compression.

        """
        reports = self.get_report_for(date_time)

        cur_reports = []
        for report in reports:
            report_dictionary = {}
            local_file_name = utils.get_local_file_name(report)
            stats_recorder = ReportStatsDBAccessor(local_file_name, None)
            stored_etag = stats_recorder.get_etag()
            LOG.info('Downloading %s for cluster ID: %s', report, self.cluster_id)
            file_name, etag = self.download_file(report, stored_etag)
            stats_recorder.update(etag=etag)
            stats_recorder.commit()

            report_dictionary['file'] = file_name
            report_dictionary['compression'] = UNCOMPRESSED
            report_dictionary['start_date'] = date_time

            cur_reports.append(report_dictionary)
        return cur_reports
