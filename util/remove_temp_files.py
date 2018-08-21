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

"""Temp file remove util functions."""

import json
import logging
import os

from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.util import common as utils

LOG = logging.getLogger(__name__)


def remove_temp_cur_files(path):
    """Remove temporary cost usage report files."""
    files = os.listdir(path)

    victim_list = []
    current_assembly_id = None
    for file in files:
        file_path = '{}/{}'.format(path, file)
        if file.endswith('Manifest.json'):
            with open(file_path, 'r') as manifest_file_handle:
                manifest_json = json.load(manifest_file_handle)
                current_assembly_id = manifest_json.get('assemblyId')
        else:
            stats = ReportStatsDBAccessor(file)
            completed_date = stats.get_last_completed_datetime()
            if completed_date:
                assembly_id = utils.extract_uuids_from_string(file).pop()

                victim_list.append({'file': file_path,
                                    'completed_date': completed_date,
                                    'assemblyId': assembly_id})

    removed_files = []
    for victim in victim_list:
        if victim['assemblyId'] != current_assembly_id:
            LOG.info('Removing %s, completed processing on date %s',
                     victim['file'], victim['completed_date'])
            os.remove(victim['file'])
            removed_files.append(victim['file'])
    return removed_files
