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

from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.processor.aws.aws_report_processor import AWSReportProcessor
from masu.processor.ocp.ocp_report_processor import OCPReportProcessor


class ReportProcessorError(Exception):
    """Report Processor error."""

    pass


# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments
class ReportProcessor:
    """Interface for masu to use to processor CUR."""

    def __init__(self, schema_name, report_path, compression, provider):
        """Set the downloader based on the backend cloud provider."""
        self.schema_name = schema_name
        self.report_path = report_path
        self.compression = compression
        self.provider_type = provider
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
                                      compression=self.compression)

        if self.provider_type in (OPENSHIFT_CONTAINER_PLATFORM, OCP_LOCAL_SERVICE_PROVIDER):
            return OCPReportProcessor(schema_name=self.schema_name,
                                      report_path=self.report_path,
                                      compression=self.compression)

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
            return self._processor.remove_temp_cur_files(path)
        except Exception as err:
            raise ReportProcessorError(str(err))

    def summarize_report_data(self, start_date, end_date=None):
        """Populate the summary tables for reporting.

        Args:
            start_date (String) The date to start populating the table.
            end_date   (String) The date to end on.

        Returns
            None

        """
        try:
            return self._processor.update_summary_tables(start_date, end_date)
        except Exception as err:
            raise ReportProcessorError(str(err))
