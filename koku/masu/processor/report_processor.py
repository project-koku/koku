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

from django.db import InterfaceError as DjangoInterfaceError
from django.db import OperationalError
from psycopg2 import InterfaceError

from api.models import Provider
from masu.processor.aws.aws_report_processor import AWSReportProcessor
from masu.processor.azure.azure_report_processor import AzureReportProcessor
from masu.processor.gcp.gcp_report_processor import GCPReportProcessor
from masu.processor.ocp.ocp_report_processor import OCPReportProcessor


LOG = logging.getLogger(__name__)


class ReportProcessorError(Exception):
    """Report Processor error."""


class ReportProcessorDBError(Exception):
    """Report Processor database error."""


class ReportProcessor:
    """Interface for masu to use to processor CUR."""

    def __init__(self, schema_name, report_path, compression, provider, provider_uuid, manifest_id):
        """Set the processor based on the data provider."""
        self.schema_name = schema_name
        self.report_path = report_path
        self.compression = compression
        self.provider_type = provider
        self.provider_uuid = provider_uuid
        self.manifest_id = manifest_id
        try:
            self._processor = self._set_processor()
        except Exception as err:
            raise ReportProcessorError(str(err))

        if not self._processor:
            raise ReportProcessorError("Invalid provider type specified.")

    def _set_processor(self):
        """
        Create the report processor object.

        Processor is specific to the provider's cloud service.

        Args:
            None

        Returns:
            (Object) : Provider-specific report processor

        """
        if self.provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return AWSReportProcessor(
                schema_name=self.schema_name,
                report_path=self.report_path,
                compression=self.compression,
                provider_uuid=self.provider_uuid,
                manifest_id=self.manifest_id,
            )

        if self.provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return AzureReportProcessor(
                schema_name=self.schema_name,
                report_path=self.report_path,
                compression=self.compression,
                provider_uuid=self.provider_uuid,
                manifest_id=self.manifest_id,
            )

        if self.provider_type in (Provider.PROVIDER_OCP,):
            return OCPReportProcessor(
                schema_name=self.schema_name,
                report_path=self.report_path,
                compression=self.compression,
                provider_uuid=self.provider_uuid,
            )
        if self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return GCPReportProcessor(
                schema_name=self.schema_name,
                report_path=self.report_path,
                compression=self.compression,
                provider_uuid=self.provider_uuid,
            )
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
        except (InterfaceError, DjangoInterfaceError, OperationalError) as err:
            raise ReportProcessorDBError(str(err))
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
