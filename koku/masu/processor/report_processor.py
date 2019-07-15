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
"""Report processor external interface."""

import logging

from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.processor.aws.aws_report_processor import AWSReportProcessor
from masu.processor.ocp.ocp_report_processor import OCPReportProcessor


LOG = logging.getLogger(__name__)


class ReportProcessorError(Exception):
    """Report Processor error."""


# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments
class ReportProcessor:
    """Interface for masu to use to processor CUR."""

    def __init__(self, schema_name, report_path, compression, provider,
                 provider_id, manifest_id):
        """Set the processor based on the data provider."""
        self.schema_name = schema_name
        self.report_path = report_path
        self.compression = compression
        self.provider_type = provider
        self.provider_id = provider_id
        self.manifest_id = manifest_id
        try:
            self._processor = self._set_processor()
        except Exception as err:
            raise ReportProcessorError(str(err))

        if not self._processor:
            raise ReportProcessorError('Invalid provider type specified.')

    def _set_processor(self):
        """
        Create the report processor object.

        Processor is specific to the provider's cloud service.

        Args:
            None

        Returns:
            (Object) : Provider-specific report processor

        """
        if self.provider_type in (AMAZON_WEB_SERVICES, AWS_LOCAL_SERVICE_PROVIDER):
            return AWSReportProcessor(schema_name=self.schema_name,
                                      report_path=self.report_path,
                                      compression=self.compression,
                                      provider_id=self.provider_id,
                                      manifest_id=self.manifest_id)

        if self.provider_type in (OPENSHIFT_CONTAINER_PLATFORM, OCP_LOCAL_SERVICE_PROVIDER):
            return OCPReportProcessor(schema_name=self.schema_name,
                                      report_path=self.report_path,
                                      compression=self.compression,
                                      provider_id=self.provider_id)

        return None

    def process(self):
        """
        Process the current cost usage report.

        Args:
            None

        Returns:
            (List) List of filenames downloaded.

        """
        try:
            return self._processor.process()
        except Exception as err:
            raise ReportProcessorError(str(err))

    def remove_processed_files(self, path):
        """
        Remove temporary cost usage report files..

        Args:
            (String) path - local path to most recent report file.

        Returns:
            [String] - List of files that were removed.

        """
        try:
            return self._processor.remove_temp_cur_files(path, self.manifest_id)
        except Exception as err:
            raise ReportProcessorError(str(err))
