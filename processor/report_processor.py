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

from masu.external import (AMAZON_WEB_SERVICES, LOCAL_SERVICE_PROVIDER)
from masu.processor.providers.aws_report_processor import AWSReportProcessor


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
        if self.provider_type in (AMAZON_WEB_SERVICES, LOCAL_SERVICE_PROVIDER):
            return AWSReportProcessor(schema_name=self.schema_name,
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
