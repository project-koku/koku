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
import calendar
import gzip
import logging
import re
from datetime import timedelta
from os import remove
from tempfile import gettempdir
from uuid import uuid4

from masu.external import (LISTEN_INGEST,
                           POLL_INGEST,
                           PROVIDER_AWS,
                           PROVIDER_AWS_LOCAL,
                           PROVIDER_AZURE,
                           PROVIDER_AZURE_LOCAL,
                           PROVIDER_GCP,
                           PROVIDER_OCP)

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
        PROVIDER_AWS: POLL_INGEST,
        PROVIDER_AWS_LOCAL: POLL_INGEST,
        PROVIDER_AZURE: POLL_INGEST,
        PROVIDER_AZURE_LOCAL: POLL_INGEST,
        PROVIDER_GCP: POLL_INGEST,
        PROVIDER_OCP: LISTEN_INGEST
    }
    return ingest_map.get(provider)


def month_date_range_tuple(for_date_time):
    """
    Get a date range tuple for the given date.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        for_date_time (DateTime): The starting datetime object

    Returns:
        (DateTime, DateTime): Tuple of first day of month,
            and first day of next month.

    """
    start_month = for_date_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, num_days = calendar.monthrange(for_date_time.year, for_date_time.month)
    first_next_month = start_month + timedelta(days=num_days)

    return start_month, first_next_month


def month_date_range(for_date_time):
    """
    Get a formatted date range string for the given date.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        for_date_time (DateTime): The starting datetime object

    Returns:
        (String): "YYYYMMDD-YYYYMMDD", example: "19701101-19701201"

    """
    start_month = for_date_time.replace(day=1, second=1, microsecond=1)
    _, num_days = calendar.monthrange(for_date_time.year, for_date_time.month)
    end_month = start_month.replace(day=num_days)
    timeformat = '%Y%m%d'
    return '{}-{}'.format(
        start_month.strftime(timeformat), end_month.strftime(timeformat)
    )


class NamedTemporaryGZip:
    """Context manager for a temporary GZip file.

    Example:
        with NamedTemporaryGZip() as temp_tz:
            temp_tz.read()
            temp_tz.write()

    """

    def __init__(self):
        """Generate a random temporary file name."""
        self.file_name = f'{gettempdir()}/{uuid4()}.gz'

    def __enter__(self):
        """Open a gz file as a fileobject."""
        self.file = gzip.open(self.file_name, 'wt')
        return self.file

    def __exit__(self, *exc):
        """Remove the temp file from disk."""
        self.file.close()
        remove(self.file_name)


def dictify_table_export_settings(table_export_settings):
    """Return a dict representation of a table_export_settings named tuple."""
    return {
        'provider': table_export_settings.provider,
        'output_name': table_export_settings.output_name,
        'iterate_daily': table_export_settings.iterate_daily,
        'sql': table_export_settings.sql
    }
