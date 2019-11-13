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
"""OCP Report Downloader."""

import datetime
import hashlib
import logging
import os
import shutil

from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.ocp import common as utils

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

LOG = logging.getLogger(__name__)


class OCPReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """OCP Cost and Usage Report Downloader."""

    # Disabling this linter until we can refactor
    # pylint: disable=too-many-arguments
    def __init__(self, task, customer_name, auth_credential, bucket, report_name=None, **kwargs):
        """
        Initializer.

        Args:
            task             (Object) bound celery object
            customer_name    (String) Name of the customer
            auth_credential  (String) OpenShift cluster ID
            report_name      (String) Name of the Cost Usage Report to download (optional)
            bucket           (String) Not used for OCP

        """
        super().__init__(task, **kwargs)

        LOG.debug('Connecting to OCP service provider...')

        self.customer_name = customer_name.replace(' ', '_')
        self.report_name = report_name
        self.cluster_id = auth_credential
        self.temp_dir = None
        self.bucket = bucket

    def _get_manifest(self, date_time):
        dates = utils.month_date_range(date_time)
        directory = '{}/{}/{}'.format(REPORTS_DIR, self.cluster_id, dates)
        LOG.info('Looking for manifest at %s', directory)
        report_meta = utils.get_report_details(directory)
        return report_meta

    def get_report_for(self, date_time):
        """
        Get OCP usage report files corresponding to a date.

        Args:
            date_time (DateTime): Start date of the usage report.

        Returns:
            ([]) List of file paths for a particular report.

        """
        dates = utils.month_date_range(date_time)
        LOG.debug('Looking for cluster %s report for date %s', self.cluster_id, str(dates))
        directory = '{}/{}/{}'.format(REPORTS_DIR, self.cluster_id, dates)

        manifest = self._get_manifest(date_time)
        LOG.info('manifest found: %s', str(manifest))
        latest_uuid = manifest.get('uuid')

        reports = []
        try:
            if latest_uuid:
                for file in os.listdir(directory):
                    if file.startswith(latest_uuid):
                        report_full_path = os.path.join(directory, file)
                        LOG.info('Found file %s', report_full_path)
                        reports.append(report_full_path)
            else:
                LOG.error('Current UUID for report could not be found.')
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
        manifest_filename = 'manifest.json'
        source_manifest_path = f'{os.path.dirname(key)}/{manifest_filename}'

        directory_path = f'{DATA_DIR}/{self.customer_name}/ocp/{self.cluster_id}'
        full_file_path = f'{directory_path}/{local_filename}'
        full_manfiest_path = f'{directory_path}/{manifest_filename}'

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        etag_hasher = hashlib.new('ripemd160')
        etag_hasher.update(bytes(local_filename, 'utf-8'))
        ocp_etag = etag_hasher.hexdigest()

        if ocp_etag != stored_etag or not os.path.isfile(full_file_path):
            LOG.info('Downloading %s to %s', key, full_file_path)
            shutil.move(key, full_file_path)
            shutil.copy2(source_manifest_path, full_manfiest_path)
        return full_file_path, ocp_etag

    def get_report_context_for_date(self, date_time):
        """
        Get the report context for a provided date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([]): List of report files.

        """
        report_dict = {}
        manifest = self._get_manifest(date_time)
        manifest_id = None
        if manifest != {}:
            manifest_id = self._prepare_db_manifest_record(manifest)

        report_dict['manifest_id'] = manifest_id
        report_dict['assembly_id'] = manifest.get('uuid')
        report_dict['compression'] = UNCOMPRESSED
        report_dict['files'] = self.get_report_for(date_time)
        return report_dict

    def get_local_file_for_report(self, report):
        """Get full path for local report file."""
        return utils.get_local_file_name(report)

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get('uuid')

        date_range = utils.month_date_range(manifest.get('date'))
        billing_str = date_range.split('-')[0]
        billing_start = datetime.datetime.strptime(billing_str, '%Y%m%d')

        num_of_files = len(manifest.get('files', []))
        return self._process_manifest_db_record(assembly_id, billing_start, num_of_files)
