#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import logging

import psutil

from api.common import log_json
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.processor.report_processor import ReportProcessor
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError

LOG = logging.getLogger(__name__)


def _process_report_file(schema_name, provider, report_dict, ingress_reports=None, ingress_reports_uuid=None):
    """
    Task to process a Report.

    Args:
        schema_name   (String) db schema name
        provider      (String) provider type
        report_dict   (dict) The report data dict from previous task

    Returns:
        None

    """
    report_path = report_dict.get("file")
    compression = report_dict.get("compression")
    manifest_id = report_dict.get("manifest_id")
    provider_uuid = report_dict.get("provider_uuid")
    tracing_id = report_dict.get("tracing_id")
    context = {
        "schema": schema_name,
        "provider_type": provider,
        "provider_uuid": provider_uuid,
        "metadata_start_date": report_dict.get("metadata_start_date"),
        "metadata_end_date": report_dict.get("metadata_end_date"),
        "compression": compression,
        "file": report_path,
        "split_files": report_dict.get("split_files"),
    }
    LOG.info(log_json(tracing_id, msg="processing report", context=context))
    mem = psutil.virtual_memory()
    mem_msg = f"Avaiable memory: {mem.free} bytes ({mem.percent}%)"
    LOG.debug(log_json(tracing_id, msg=mem_msg, context=context))

    file_name = report_path.split("/")[-1]
    with ReportStatsDBAccessor(file_name, manifest_id) as stats_recorder:
        stats_recorder.log_last_started_datetime()

    try:
        processor = ReportProcessor(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider=provider,
            provider_uuid=provider_uuid,
            manifest_id=manifest_id,
            context=report_dict,
            ingress_reports=ingress_reports,
            ingress_reports_uuid=ingress_reports_uuid,
        )

        result = processor.process()
    except (ReportProcessorError, ReportProcessorDBError) as processing_error:
        with ReportStatsDBAccessor(file_name, manifest_id) as stats_recorder:
            stats_recorder.clear_last_started_datetime()
        raise processing_error
    except NotImplementedError as err:
        with ReportStatsDBAccessor(file_name, manifest_id) as stats_recorder:
            stats_recorder.log_last_completed_datetime()
        raise err

    with ReportStatsDBAccessor(file_name, manifest_id) as stats_recorder:
        stats_recorder.log_last_completed_datetime()

    with ReportManifestDBAccessor() as manifest_accesor:
        manifest = manifest_accesor.get_manifest_by_id(manifest_id)
        if manifest:
            manifest_accesor.mark_manifest_as_updated(manifest)
        else:
            LOG.error(
                log_json(
                    tracing_id, msg=f"Unable to find manifest for ID: {manifest_id}, file {file_name}", context=context
                )
            )

    with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
        provider_accessor.setup_complete()

    return result
