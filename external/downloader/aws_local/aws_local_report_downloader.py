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
"""AWS Local Report Downloader."""

# pylint: skip-file
# Having trouble disabling the lint warning for duplicate-code (AWSReportDownloader..)
# Disabling pylint on this file since AWSLocalReportDownloader is a DEBUG feature.

import datetime
import hashlib
import json
import logging
import os
import re
import shutil

from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws import common as utils

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AWSLocalReportDownloader(ReportDownloaderBase, DownloaderInterface):
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
        prefix, name = self._extract_names(bucket)

        if report_name:
            self.report_name = report_name
        else:
            self.report_name = name
        self.report_prefix = prefix

        LOG.info('Found report name: %s, report prefix: %s', self.report_name, self.report_prefix)
        if self.report_prefix:
            self.base_path = '{}/{}/'.format(bucket, self.report_prefix)
        else:
            self.base_path = bucket
        self.bucket_path = bucket
        self.bucket = bucket.replace('/', '_')
        self.credential = auth_credential
        self.provider_id = None
        if 'provider_id' in kwargs:
            self._provider_id = kwargs['provider_id']

    @property
    def manifest_date_format(self):
        """Set the AWS manifest date format."""
        return '%Y%m%dT000000.000Z'

    def _extract_names(self, bucket):
        """
        Find the report name and prefix given the bucket path.

        Args:
            bucket (String): Path to the local file

        Returns:
            (String, String) report_prefix, report_name

        """
        daterange = '\d{8}-\d{8}'
        full_path = ''
        for item in os.walk(bucket, followlinks=True):
            if not item[2]:
                if any(re.findall(daterange, date) for date in item[1]):
                    full_path = item[0]
                    break
        directories = full_path[len(bucket):]

        report_prefix = None
        report_name = None
        if directories:
            parts = directories.strip('/').split('/')
            report_name = parts.pop()
            report_prefix = parts.pop() if parts else None
        return report_prefix, report_name

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

    def download_file(self, key, stored_etag=None):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        local_s3_filename = utils.get_local_file_name(key)

        directory_path = f'{DATA_DIR}/{self.customer_name}/aws-local/{self.bucket}'
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
        assembly_id = manifest.get('assemblyId')
        manifest_id = self._process_manifest_db_record(manifest)

        reports = manifest.get('reportKeys')

        cur_reports = []
        for report in reports:
            report_dictionary = {}
            local_s3_filename = utils.get_local_file_name(report)
            stats_recorder = ReportStatsDBAccessor(
                local_s3_filename,
                manifest_id
            )
            stored_etag = stats_recorder.get_etag()
            report_path = self.bucket_path + '/' + report
            LOG.info('Downloading %s with credential %s', report_path, self.credential)
            file_name, etag = self.download_file(report_path, stored_etag)
            stats_recorder.update(etag=etag)
            stats_recorder.commit()

            report_dictionary['file'] = file_name
            report_dictionary['compression'] = 'GZIP'
            report_dictionary['start_date'] = date_time
            report_dictionary['assembly_id'] = assembly_id
            report_dictionary['manifest_id'] = manifest_id

            cur_reports.append(report_dictionary)
        return cur_reports

    def _process_manifest_db_record(self, manifest):
        """Insert or update the manifest DB record."""
        LOG.info(f'Upserting manifest database record: ')

        assembly_id = manifest.get('assemblyId')

        manifest_accessor = ReportManifestDBAccessor()
        manifest_entry = manifest_accessor.get_manifest(
            assembly_id,
            self._provider_id
        )

        if not manifest_entry:
            billing_str = manifest.get('billingPeriod', {}).get('start')
            billing_start = datetime.datetime.strptime(
                billing_str,
                self.manifest_date_format
            )
            manifest_dict = {
                'assembly_id': assembly_id,
                'billing_period_start_datetime': billing_start,
                'num_total_files': len(manifest.get('reportKeys', [])),
                'provider_id': self._provider_id
            }
            manifest_entry = manifest_accessor.add(manifest_dict)

        manifest_accessor.mark_manifest_as_updated(manifest_entry)
        manifest_accessor.commit()
        manifest_id = manifest_entry.id
        manifest_accessor.close_session()

        return manifest_id
