#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report processor external interface."""
import logging
from functools import cached_property

from django.db import InterfaceError as DjangoInterfaceError
from django.db import OperationalError
from psycopg2 import InterfaceError
from requests.exceptions import ConnectionError
from requests.exceptions import ConnectTimeout
from requests.exceptions import InvalidURL

from api.common import log_json
from api.models import Provider
from masu.processor import enable_trino_processing
from masu.processor.aws.aws_report_processor import AWSReportProcessor
from masu.processor.azure.azure_report_processor import AzureReportProcessor
from masu.processor.gcp.gcp_report_processor import GCPReportProcessor
from masu.processor.ocp.ocp_report_processor import OCPReportProcessor
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor

LOG = logging.getLogger(__name__)


class ReportProcessorError(Exception):
    """Report Processor error."""


class ReportProcessorDBError(Exception):
    """Report Processor database error."""


class ReportProcessor:
    """Interface for masu to use to processor CUR."""

    def __init__(self, schema_name, report_path, compression, provider, provider_uuid, manifest_id, context=None):
        """Set the processor based on the data provider."""
        self.schema_name = schema_name
        self.report_path = report_path
        self.compression = compression
        self.provider_type = provider
        self.provider_uuid = provider_uuid
        self.manifest_id = manifest_id
        self.context = context
        self.tracing_id = context.get("tracing_id") if context else None
        try:
            self._processor, self._secondary_processor = self._set_processor()
        except NotImplementedError as err:
            raise err
        except Exception as err:
            raise ReportProcessorError(str(err))

        if not self._processor:
            raise ReportProcessorError("Invalid provider type specified.")

    @cached_property
    def trino_enabled(self):
        """Return whether the source is enabled for Trino processing."""
        return enable_trino_processing(self.provider_uuid, self.provider_type, self.schema_name)

    @property
    def ocp_on_cloud_processor(self):
        """Return the OCP on Cloud processor if one is defined."""
        if self.trino_enabled and self.provider_type in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
            return OCPCloudParquetReportProcessor(
                schema_name=self.schema_name,
                report_path=self.report_path,
                provider_uuid=self.provider_uuid,
                provider_type=self.provider_type,
                manifest_id=self.manifest_id,
                context=self.context,
            )
        return None

    def _set_processor(self):
        """
        Create the report processor object.

        Processor is specific to the provider's cloud service.

        Args:
            None

        Returns:
            (Object) : Provider-specific report processor

        """
        if self.trino_enabled:
            return (
                ParquetReportProcessor(
                    schema_name=self.schema_name,
                    report_path=self.report_path,
                    provider_uuid=self.provider_uuid,
                    provider_type=self.provider_type,
                    manifest_id=self.manifest_id,
                    context=self.context,
                ),
                None,
            )
        if self.provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return (
                AWSReportProcessor(
                    schema_name=self.schema_name,
                    report_path=self.report_path,
                    compression=self.compression,
                    provider_uuid=self.provider_uuid,
                    manifest_id=self.manifest_id,
                ),
                None,
            )

        if self.provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return (
                AzureReportProcessor(
                    schema_name=self.schema_name,
                    report_path=self.report_path,
                    compression=self.compression,
                    provider_uuid=self.provider_uuid,
                    manifest_id=self.manifest_id,
                ),
                None,
            )

        if self.provider_type in (Provider.PROVIDER_OCP,):
            return (
                OCPReportProcessor(
                    schema_name=self.schema_name,
                    report_path=self.report_path,
                    compression=self.compression,
                    provider_uuid=self.provider_uuid,
                ),
                ParquetReportProcessor(
                    schema_name=self.schema_name,
                    report_path=self.report_path,
                    provider_uuid=self.provider_uuid,
                    provider_type=self.provider_type,
                    manifest_id=self.manifest_id,
                    context=self.context,
                ),
            )
        if self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return (
                GCPReportProcessor(
                    schema_name=self.schema_name,
                    report_path=self.report_path,
                    compression=self.compression,
                    provider_uuid=self.provider_uuid,
                    manifest_id=self.manifest_id,
                ),
                None,
            )
        return None, None

    def process(self):
        """
        Process the current cost usage report.

        Args:
            None

        Returns:
            (List) List of filenames downloaded.

        """
        msg = f"Report processing started for {self.report_path}"
        LOG.info(log_json(self.tracing_id, msg))
        try:
            if self.trino_enabled:
                parquet_base_filename, daily_data_frames = self._processor.process()
                if self.ocp_on_cloud_processor:
                    self.ocp_on_cloud_processor.process(parquet_base_filename, daily_data_frames)
                return
            msg = f"Report processing completed for {self.report_path}"
            LOG.info(log_json(self.tracing_id, msg))
            if self._secondary_processor:
                try:
                    self._secondary_processor.process()
                except (ConnectTimeout, InvalidURL, ConnectionError):
                    pass
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
