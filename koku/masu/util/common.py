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

"""Common util functions."""
import logging
import re
from os import listdir, remove

from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           AZURE,
                           AZURE_LOCAL_SERVICE_PROVIDER,
                           LISTEN_INGEST,
                           OPENSHIFT_CONTAINER_PLATFORM,
                           POLL_INGEST)

LOG = logging.getLogger(__name__)


def extract_uuids_from_string(source_string):
    """
    Extract uuids out of a given source string.

    Args:
        source_string (Source): string to locate UUIDs.

    Returns:
        ([]) List of UUIDs found in the source string

    """
    uuid_regex = '[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
    found_uuid = re.findall(uuid_regex, source_string, re.IGNORECASE)
    return found_uuid


def stringify_json_data(data):
    """Convert each leaf value of a JSON object to string."""
    if isinstance(data, list):
        for i, entry in enumerate(data):
            data[i] = stringify_json_data(entry)
    elif isinstance(data, dict):
        for key in data:
            data[key] = stringify_json_data(data[key])
    elif not isinstance(data, str):
        return str(data)

    return data


def ingest_method_for_provider(provider):
    """Return the ingest method for provider."""
    ingest_map = {
        AMAZON_WEB_SERVICES: POLL_INGEST,
        AWS_LOCAL_SERVICE_PROVIDER: POLL_INGEST,
        AZURE: POLL_INGEST,
        AZURE_LOCAL_SERVICE_PROVIDER: POLL_INGEST,
        OPENSHIFT_CONTAINER_PLATFORM: LISTEN_INGEST
    }
    return ingest_map.get(provider)


def clear_temp_directory(report_path, current_assembly_id, prefix=None):
    """Remove temporary files from masu temp directory."""
    files = listdir(report_path)
    removed_files = []
    for file in files:
        file_path = '{}/{}'.format(report_path, file)
        if prefix:
            file = prefix + file
        completed_date = None
        with ReportStatsDBAccessor(file, None) as stats:
            completed_date = stats.get_completion_time_for_report(file)
        if completed_date:
            uuids = extract_uuids_from_string(file_path)
            assembly_id = uuids.pop() if uuids else None
            if assembly_id and assembly_id != current_assembly_id:
                try:
                    LOG.info('Removing %s, Completed on %s', file_path, str(completed_date))
                    remove(file_path)
                    removed_files.append(file_path)
                except FileNotFoundError:
                    LOG.warning('Unable to locate file: %s', file_path)
    return removed_files
