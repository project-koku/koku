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
from dateutil.relativedelta import relativedelta

from masu.processor.exceptions import MasuConfigurationError
from masu.processor.report_downloader import ReportDownloader
from masu.providers import DATA_DIR
from masu.providers.aws.sts import get_assume_role_session

LOG = logging.getLogger(__name__)


class AWSReportDownloader(ReportDownloader):
    """
    AWS Cost and Usage Report Downloader.

    For configuration of AWS, see
    https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-costusage.html
    """

    def __init__(self, customer, provider, report_stats, **kwargs):
        """
        Constructor.

        Args:
            customer     (CustomerDBAccessor) the customer accessor
            provider     (ProviderAuthDBAccessor) the provider accessor
            report_stats (ReportStatsDBAccessor) the report stats accessor

        """
        super().__init__(**kwargs)

        self.provider = provider
        self.customer = customer
        self.report_stats = report_stats

        self.customer_schema = self.customer.get_schema_name()

        LOG.debug('Connecting to AWS...')
        session = get_assume_role_session(
            arn=self.provider.get_provider_resource_name(),
            session='MasuDownloaderSession')
        self.cur = session.client('cur')

        defs = self.cur.describe_report_definitions()
        self.report_name = self.provider.get_report_name()
        report_defs = defs.get('ReportDefinitions', [])
        report = [rep for rep in report_defs
                  if rep['ReportName'] == self.report_name].pop()

        if not report:
            raise MasuConfigurationError('Cost and Usage Report definition not found.')

        self.region = report['S3Region']
        self.bucket = report['S3Bucket']
        self.bucket_prefix = report['S3Prefix']

        self.s3 = session.client('s3')

    def _get_manifest(self, dt):
        """
        Download and return the CUR manifest for the given date.

        Args:
            dt (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        manifest = '{}/{}-Manifest.json'.format(self._get_report_path(dt),
                                                self.report_name)
        manifest_file = self.download_file(manifest)

        manifest_json = None
        with open(manifest_file, 'r') as f:
            manifest_json = json.load(f)

        return manifest_json

    def _get_report_path(self, dt):
        """
        Return path of report files.

        Args:
            dt (DateTime): The starting datetime object

        Returns:
            (String): "/prefix/report_name/YYYYMMDD-YYYYMMDD",
                    example: "/my-prefix/my-report/19701101-19701201"

        """
        report_date_range = self._get_manifest_date_range(dt)
        return '{}/{}/{}'.format(self.bucket_prefix,
                                 self.report_name,
                                 report_date_range)

    def _get_manifest_date_range(self, dt):
        """
        Get a formatted date range string.

        Args:
            dt (DateTime): The starting datetime object

        Returns:
            (String): "YYYYMMDD-YYYYMMDD", example: "19701101-19701201"

        """
        start_month = dt.replace(day=1, second=1, microsecond=1)
        end_month = start_month + relativedelta(months=+1)
        timeformat = '%Y%m%d'
        return '{}-{}'.format(start_month.strftime(timeformat),
                              end_month.strftime(timeformat))

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
            files.append(self.download_file(s3obj.key))
        return files

    def download_current_report(self):
        """
        Read CUR manifest, download current report files.

        Returns:
            (List) List of filenames downloaded.

        """
        return self.download_report(datetime.today())

    def download_file(self, key):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        s3_filename = key.split('/')[-1]
        file_path = f'{DATA_DIR}/{self.customer_schema}/aws'
        file_name = f'{file_path}/{s3_filename}'
        # Make sure the data directory exists
        os.makedirs(file_path, exist_ok=True)

        etag = self.report_stats.get_etag(key)
        s3_file = self.s3.get_object(Bucket=self.bucket, Key=key)
        if s3_file.get('etag') != etag:
            LOG.info('Downloading %s to %s', s3_filename, file_name)
            self.s3.download_file(self.bucket, key, file_name)
            self.report_stats.update(report_name=key,
                                     etag=s3_file.get('etag'),
                                     last_completed_datetime=datetime.now())
        return file_name

    def download_report(self, dt):
        """
        Download CUR for a given date.

        Args:
            dt (DateTime): The starting datetime object

        Returns:
            (List) List of filenames downloaded.

        """
        manifest = self._get_manifest(dt)
        reports = manifest.get('reportKeys')

        files = []
        for report in reports:
            files.append(self.download_file(report))
        return files
