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
"""AWS CUR Downloader."""

import json
import logging
import os
from datetime import datetime

import boto3

import masu.external.downloader.aws.aws_utils as utils
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.processor.exceptions import MasuConfigurationError
from masu.providers import DATA_DIR

LOG = logging.getLogger(__name__)


class AWSReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    AWS Cost and Usage Report Downloader.

    For configuration of AWS, see
    https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-costusage.html
    """

    def __init__(self, customer_name, auth_credential, cur_source, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            auth_credential  (String) Authentication credential for S3 bucket (RoleARN)
            report_name      (String) Name of the Cost Usage Report to download (optional)
            cur_source       (String) Name of the S3 bucket containing the CUR

        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(' ', '_')

        LOG.debug('Connecting to AWS...')
        session = utils.establish_aws_session(auth_credential, 'MasuDownloaderSession')
        self.cur = session.client('cur')

        if not report_name:
            available_reports = utils.get_cur_report_names_in_bucket(auth_credential, cur_source)
            # Get the first report in the bucket until Koku can specify which CUR the user wants
            if available_reports:
                report_name = available_reports[0]
        self.report_name = report_name

        report_defs = utils.get_cur_report_definitions(auth_credential, session)
        report = [rep for rep in report_defs
                  if rep['ReportName'] == self.report_name]

        if not report:
            raise MasuConfigurationError('Cost and Usage Report definition not found.')

        report_to_download = report.pop()
        self.region = report_to_download['S3Region']
        self.bucket = cur_source
        self.bucket_prefix = report_to_download['S3Prefix']

        self.s3_client = session.client('s3')

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
        return '{}/{}/{}'.format(self.bucket_prefix,
                                 self.report_name,
                                 report_date_range)

    def download_bucket(self):
        """
        Bulk Download all files in an s3 bucket.

        Returns:
            (List) List of filenames downloaded.

        """
        s3_resource = boto3.resource('s3')
        bucket = s3_resource.Bucket(self.bucket)
        files = []
        for s3obj in bucket.objects.all():
            file_name, _ = self.download_file(s3obj.key)
            files.append(file_name)
        return files

    def download_current_report(self):
        """
        Read CUR manifest, download current report files.

        Returns:
            (List) List of filenames downloaded.

        """
        return self.download_report(datetime.today())

    def download_file(self, key, stored_etag=None):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        s3_filename = key.split('/')[-1]
        file_path = f'{DATA_DIR}/{self.customer_name}/aws'
        file_name = f'{file_path}/{s3_filename}'
        # Make sure the data directory exists
        os.makedirs(file_path, exist_ok=True)

        s3_file = self.s3_client.get_object(Bucket=self.bucket, Key=key)
        s3_etag = s3_file.get('ETag')
        if s3_etag != stored_etag:
            LOG.info('Downloading %s to %s', s3_filename, file_name)
            self.s3_client.download_file(self.bucket, key, file_name)
        return file_name, s3_etag

    def download_report(self, date_time):
        """
        Download CUR for a given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (List) List of filenames downloaded.

        """
        manifest = self._get_manifest(date_time)
        reports = manifest.get('reportKeys')

        files = []
        for report in reports:
            s3_filename = report.split('/')[-1]
            stats_recorder = ReportStatsDBAccessor(s3_filename)
            stored_etag = stats_recorder.get_etag()

            file_name, etag = self.download_file(report, stored_etag)
            stats_recorder.update(etag=etag)
            stats_recorder.commit()

            files.append(file_name)
        return files
