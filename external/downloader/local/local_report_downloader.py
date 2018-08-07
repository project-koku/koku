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
"""Local Report Downloader."""

# pylint: skip-file
# Having trouble disabling the lint warning for duplicate-code (AWSReportDownloader..)
# Disabling pylint on this file since LocalReportDownloader is a DEBUG feature.

import hashlib
import json
import logging
import os
import shutil

from masu.config import Config
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.aws import utils
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class LocalReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """Local Cost and Usage Report Downloader."""

    def __init__(self, customer_name, auth_credential, bucket, report_name=None, **kwargs):
        """
        Initializer.

        Args:
            customer_name    (String) Name of the customer
            auth_credential  (String) Authentication credential for S3 bucket (RoleARN)
            report_name      (String) Name of the Cost Usage Report to download (optional)
            bucket           (String) Name of the S3 bucket containing the CUR

        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(' ', '_')

        LOG.debug('Connecting to local service provider...')

        if report_name:
            self.report_name = report_name
        else:
            self.report_name = os.listdir(bucket)[0]
        self.base_path = bucket
        self.bucket = bucket.replace('/', '_')
        self.credential = auth_credential

    def _get_manifest(self, date_time):
        """
        Download and return the CUR manifest for the given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        manifest = '{}/{}-Manifest.json'.format(self._get_report_path(date_time),
                                                self.report_name)

        manifest_file, _ = self.download_file(manifest)

        manifest_json = None
        with open(manifest_file, 'r') as manifest_file_handle:
            manifest_json = json.load(manifest_file_handle)

        return manifest_json

    def _get_report_path(self, date_time):
        """
        Return path of report files.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (String): "/prefix/report_name/YYYYMMDD-YYYYMMDD",
                    example: "/my-prefix/my-report/19701101-19701201"

        """
        report_date_range = utils.month_date_range(date_time)
        return '{}/{}/{}'.format(self.base_path,
                                 self.report_name,
                                 report_date_range)

    def download_current_report(self):
        """
        Read CUR manifest, download current report files.

        Returns:
            (List) List of filenames downloaded.

        """
        return self.download_report(DateAccessor().today())

    def download_file(self, key, stored_etag=None):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        local_s3_filename = utils.get_local_file_name(key)

        directory_path = f'{DATA_DIR}/{self.customer_name}/local/{self.bucket}'
        full_file_path = f'{directory_path}/{local_s3_filename}'

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        s3_etag_hasher = hashlib.new('ripemd160')
        s3_etag_hasher.update(bytes(local_s3_filename, 'utf-8'))
        s3_etag = s3_etag_hasher.hexdigest()

        if s3_etag != stored_etag or not os.path.isfile(full_file_path):
            LOG.info('Downloading %s to %s', key, full_file_path)
            shutil.copy2(key, full_file_path)
        return full_file_path, s3_etag

    def download_report(self, date_time):
        """
        Download CUR for a given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ([{}]) List of dictionaries containing file path and compression.

        """
        manifest = self._get_manifest(date_time)
        reports = manifest.get('reportKeys')

        cur_reports = []
        report_dictionary = {}
        for report in reports:
            local_s3_filename = utils.get_local_file_name(report)
            stats_recorder = ReportStatsDBAccessor(local_s3_filename)
            stored_etag = stats_recorder.get_etag()
            report_path = self.base_path + report
            LOG.info('Downloading %s with credential %s', report_path, self.credential)
            file_name, etag = self.download_file(report_path, stored_etag)
            stats_recorder.update(etag=etag)
            stats_recorder.commit()

            report_dictionary['file'] = file_name
            report_dictionary['compression'] = 'GZIP'

            cur_reports.append(report_dictionary)
        return cur_reports
