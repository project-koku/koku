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
import re

from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           LISTEN_INGEST,
                           OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM,
                           POLL_INGEST)


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
        OCP_LOCAL_SERVICE_PROVIDER: POLL_INGEST,
        OPENSHIFT_CONTAINER_PLATFORM: LISTEN_INGEST
    }
    return ingest_map.get(provider)
