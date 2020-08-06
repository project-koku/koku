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
"""Asynchronous tasks."""
from os import path

import psutil
from celery.utils.log import get_task_logger

from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.processor.report_processor import ReportProcessor
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError

LOG = get_task_logger(__name__)


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
    log_statement = (
        f"Processing Report:\n"
        f" schema_name: {schema_name}\n"
        f" provider: {provider}\n"
        f" provider_uuid: {provider_uuid}\n"
        f" file: {report_path}\n"
        f" compression: {compression}\n"
        f" start_date: {start_date}"
    )
    LOG.info(log_statement)
    mem = psutil.virtual_memory()
    mem_msg = f"Avaiable memory: {mem.free} bytes ({mem.percent}%)"
    LOG.info(mem_msg)

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
        )

        processor.process()
    except (ReportProcessorError, ReportProcessorDBError) as processing_error:
        with ReportStatsDBAccessor(file_name, manifest_id) as stats_recorder:
            stats_recorder.clear_last_started_datetime()
        raise processing_error

    with ReportStatsDBAccessor(file_name, manifest_id) as stats_recorder:
        stats_recorder.log_last_completed_datetime()

    with ReportManifestDBAccessor() as manifest_accesor:
        manifest = manifest_accesor.get_manifest_by_id(manifest_id)
        if manifest:
            manifest_accesor.mark_manifest_as_updated(manifest)
        else:
            LOG.error("Unable to find manifest for ID: %s, file %s", manifest_id, file_name)

    with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
        if provider_accessor.get_setup_complete():
            files = processor.remove_processed_files(path.dirname(report_path))
            LOG.info("Temporary files removed: %s", str(files))
        provider_accessor.setup_complete()

    return True
