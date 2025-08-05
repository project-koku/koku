#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report processor external interface."""
import logging
from pathlib import Path

from django.db import InterfaceError as DjangoInterfaceError
from django.db import OperationalError
from psycopg2 import InterfaceError

from api.common import log_json
from koku.database_exc import get_extended_exception_by_type
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ReportsAlreadyProcessed
from reporting_common.models import CombinedChoices
from reporting_common.models import CostUsageReportStatus

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
        try:
            self._processor = self._set_processor()
        except Exception as err:
            raise ReportProcessorError(str(err)) from err

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
        )

    def process(self):
        """
        Process the current cost usage report.

        Args:
            None

        Returns:
            (List) List of filenames downloaded.

        """
        msg = f"report processing started for {self.report_path}"
        report_status = CostUsageReportStatus.objects.get(
            report_name=Path(self.report_path).name, manifest_id=self.manifest_id
        )
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        try:
            return self._processor.process()
        except ReportsAlreadyProcessed:
            report_status.update_status(CombinedChoices.DONE)
            LOG.info(log_json(msg="report already processed", context=self.context))
            return True
        except (InterfaceError, DjangoInterfaceError) as err:
            report_status.update_status(CombinedChoices.FAILED)
            raise ReportProcessorDBError(f"Interface error: {err}") from err
        except OperationalError as o_err:
            report_status.update_status(CombinedChoices.FAILED)
            db_exc = get_extended_exception_by_type(o_err)
            LOG.error(log_json(self.tracing_id, msg=f"Operation error: {db_exc}", context=db_exc.as_dict()))
            raise db_exc from o_err
        except Exception as err:
            report_status.update_status(CombinedChoices.FAILED)
            raise ReportProcessorError(f"Unknown processor error: {err}") from err
