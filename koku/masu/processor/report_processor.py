#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report processor external interface."""
import logging

from django.db import InterfaceError as DjangoInterfaceError
from django.db import OperationalError
from psycopg2 import InterfaceError

from api.common import log_json
from api.models import Provider
from koku.database_exc import get_extended_exception_by_type
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor

LOG = logging.getLogger(__name__)


class ReportProcessorError(Exception):
    """Report Processor error."""


class ReportProcessorDBError(Exception):
    """Report Processor database error."""


class ReportProcessor:
    """Interface for masu to use to processor CUR."""

    def __init__(
        self,
        schema_name,
        report_path,
        compression,
        provider,
        provider_uuid,
        manifest_id,
        context=None,
        ingress_reports=None,
        ingress_reports_uuid=None,
        ingress_report_counter=None,
    ):
        """Set the processor based on the data provider."""
        self.schema_name = schema_name
        self.report_path = report_path
        self.compression = compression
        self.provider_type = provider
        self.provider_uuid = provider_uuid
        self.manifest_id = manifest_id
        self.context = context
        self.tracing_id = context.get("tracing_id") if context else None
        self.ingress_reports = ingress_reports
        self.ingress_reports_uuid = ingress_reports_uuid
        self.ingress_report_counter = ingress_report_counter
        try:
            self._processor = self._set_processor()
        except Exception as err:
            raise ReportProcessorError(str(err)) from err

    @property
    def ocp_on_cloud_processor(self):
        """Return the OCP on Cloud processor if one is defined."""
        if self.provider_type in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
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
        return ParquetReportProcessor(
            schema_name=self.schema_name,
            report_path=self.report_path,
            provider_uuid=self.provider_uuid,
            provider_type=self.provider_type,
            manifest_id=self.manifest_id,
            context=self.context,
            ingress_reports=self.ingress_reports,
            ingress_reports_uuid=self.ingress_reports_uuid,
            ingress_report_counter=self.ingress_report_counter,
        )

    def process(self):
        """
        Process the current cost usage report.

        Args:
            None

        Returns:
            (List) List of filenames downloaded.

        """
        msg = f"Report processing started for {self.report_path}"
        LOG.info(log_json(self.tracing_id, msg=msg))
        try:
            parquet_base_filename, daily_data_frames = self._processor.process()
            if self.ocp_on_cloud_processor:
                self.ocp_on_cloud_processor.process(parquet_base_filename, daily_data_frames)
            if daily_data_frames != []:
                return True
            else:
                return False
        except (InterfaceError, DjangoInterfaceError) as err:
            raise ReportProcessorDBError(f"Interface error: {err}") from err
        except OperationalError as o_err:
            db_exc = get_extended_exception_by_type(o_err)
            LOG.error(log_json(self.tracing_id, msg=f"Operation error: {db_exc}", context=db_exc.as_dict()))
            raise db_exc from o_err
        except Exception as err:
            raise ReportProcessorError(f"Unknown processor error: {err}") from err
