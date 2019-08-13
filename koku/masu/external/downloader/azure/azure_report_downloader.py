#
# Copyright 2019 Red Hat, Inc.
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
"""Azure Report Downloader."""

# pylint: disable=fixme
# disabled until we get travis to not fail on warnings, or the fixme is
# resolved.

import datetime
import json
import logging
import os
import shutil
import struct

import boto3
from botocore.exceptions import ClientError

from masu.config import Config
from masu.exceptions import MasuProviderError
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.azure import common as utils
from masu.external.downloader.azure.azure_service import AzureService

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AzureReportDownloaderError(Exception):
    """AWS Report Downloader error."""


class AzureReportDownloaderNoFileError(Exception):
    """AWS Report Downloader error for missing file."""


class AzureReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    Azure Cost and Usage Report Downloader.

    """

    empty_manifest = {'reportKeys': []}

    def __init__(self, customer_name, auth_credential, bucket, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            auth_credential  (String) Authentication credential for S3 bucket (RoleARN)
            report_name      (String) Name of the Cost Usage Report to download (optional)
            bucket           (String) Name of the S3 bucket containing the CUR

        """
        super().__init__(**kwargs)
        resource_group_name = auth_credential.get('resource_group_name') #'RG1'
        storage_account_name = auth_credential.get('storage_account_name') #'mysa1'
        container_name = bucket #'output'
        export_name = report_name #'cost/costreport'
        blob = AzureService().get_latest_cost_export(
            resource_group_name, storage_account_name, container_name, export_name)
        print(f'{blob.name} = {blob.properties.etag} - {blob.properties.last_modified}')
        
    def get_report_context_for_date(self, date_time):
        pass

    def get_local_file_for_report(self, report):
        pass

    def download_file(self, key, stored_etag=None):
        pass
    