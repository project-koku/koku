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
"""Processing asynchronous tasks."""

import logging

from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.processor.report_processor import ReportProcessor

LOG = logging.getLogger(__name__)


def process_report_file(process_request):
    """
    Task to process a Cost Usage Report.

    Args:
        process_request (CURProcessRequest): Attributes for report processing.

    Returns:
        None

    """
    stmt = ('Processing Report:'
            ' schema_name: {},'
            ' report_path: {},'
            ' compression: {}')
    log_statement = stmt.format(process_request.schema_name,
                                process_request.report_path,
                                process_request.compression)
    LOG.info(log_statement)

    file_name = process_request.report_path.split('/')[-1]
    stats_recorder = ReportStatsDBAccessor(file_name)
    cursor_position = stats_recorder.get_cursor_position()

    processor = ReportProcessor(schema_name=process_request.schema_name,
                                report_path=process_request.report_path,
                                compression=process_request.compression,
                                cursor_pos=cursor_position)

    stats_recorder.log_last_started_datetime()
    last_cursor_position = processor.process()
    stats_recorder.log_last_completed_datetime()
    stats_recorder.set_cursor_position(last_cursor_position)
    stats_recorder.commit()
