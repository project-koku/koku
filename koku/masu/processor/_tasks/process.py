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


def _process_report_file(schema_name, provider, report_dict):
    """
    Task to process a Report.

    Args:
        schema_name   (String) db schema name
        provider      (String) provider type
        report_dict   (dict) The report data dict from previous task

    Returns:
        None

    """
    start_date = report_dict.get("start_date")
    report_path = report_dict.get("file")
    compression = report_dict.get("compression")
    manifest_id = report_dict.get("manifest_id")
    provider_uuid = report_dict.get("provider_uuid")
    tracing_id = report_dict.get("tracing_id")
    log_statement = (
        f"Processing Report: "
        f" schema_name: {schema_name} "
        f" provider: {provider} "
        f" provider_uuid: {provider_uuid} "
        f" file: {report_path} "
        f" compression: {compression} "
        f" start_date: {start_date} "
    )
    LOG.info(log_json(tracing_id, log_statement))
    mem = psutil.virtual_memory()
    mem_msg = f"Avaiable memory: {mem.free} bytes ({mem.percent}%)"
    LOG.debug(log_json(tracing_id, mem_msg))

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
        )

        processor.process()
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
            LOG.error(log_json(tracing_id, ("Unable to find manifest for ID: %s, file %s", manifest_id, file_name)))

    with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
        provider_accessor.setup_complete()

    return True
