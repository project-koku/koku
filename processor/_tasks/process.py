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

import masu.util.remove_temp_files as remove_files
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.processor.report_processor import ReportProcessor

LOG = get_task_logger(__name__)


def _process_report_file(schema_name, report_path, compression, provider):
    """
    Task to process a Report.

    Args:
        schema_name (String) db schema name
        report_path (String) path to downloaded reports
        compression (String) 'PLAIN' or 'GZIP'
        provider    (String) provider type

    Returns:
        None

    """
    stmt = ('Processing Report:'
            ' schema_name: {},'
            ' report_path: {},'
            ' compression: {},'
            ' provider: {}')
    log_statement = stmt.format(schema_name,
                                report_path,
                                compression,
                                provider)
    LOG.info(log_statement)
    mem = psutil.virtual_memory()
    mem_msg = 'Avaiable memory: {} bytes ({}%)'.format(mem.free, mem.percent)
    LOG.info(mem_msg)

    file_name = report_path.split('/')[-1]

    stats_recorder = ReportStatsDBAccessor(file_name)
    stats_recorder.log_last_started_datetime()
    stats_recorder.commit()

    processor = ReportProcessor(schema_name=schema_name,
                                report_path=report_path,
                                compression=compression,
                                provider=provider)

    processor.process()
    stats_recorder.log_last_completed_datetime()
    stats_recorder.commit()
    stats_recorder.close_session()

    files = remove_files.remove_temp_cur_files(path.dirname(report_path))
    LOG.info('Temporary files removed: %s', str(files))
