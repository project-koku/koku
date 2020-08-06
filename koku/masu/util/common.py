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
import json
import logging
import re
from datetime import timedelta
from os import remove
from tempfile import gettempdir
from uuid import uuid4

import pandas as pd
from dateutil import parser
from dateutil.rrule import DAILY
from dateutil.rrule import rrule

from api.models import Provider
from masu.config import Config
from masu.external import LISTEN_INGEST
from masu.external import POLL_INGEST
from masu.util.ocp.common import process_openshift_datetime
from masu.util.ocp.common import process_openshift_labels

LOG = logging.getLogger(__name__)


def extract_uuids_from_string(source_string):
    """
    Extract uuids out of a given source string.

    Args:
        source_string (Source): string to locate UUIDs.

    Returns:
        ([]) List of UUIDs found in the source string

    """
    uuid_regex = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
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
        Provider.PROVIDER_AWS: POLL_INGEST,
        Provider.PROVIDER_AWS_LOCAL: POLL_INGEST,
        Provider.PROVIDER_AZURE: POLL_INGEST,
        Provider.PROVIDER_AZURE_LOCAL: POLL_INGEST,
        Provider.PROVIDER_GCP: POLL_INGEST,
        Provider.PROVIDER_OCP: LISTEN_INGEST,
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
    start_month = for_date_time.replace(day=1)
    _, num_days = calendar.monthrange(for_date_time.year, for_date_time.month)
    end_month = start_month.replace(day=num_days)
    timeformat = "%Y%m%d"
    return "{}-{}".format(start_month.strftime(timeformat), end_month.strftime(timeformat))


def safe_float(val):
    """
    Convert the given value to a float or 0f.
    """
    result = float(0)
    try:
        result = float(val)
    except (ValueError, TypeError):
        pass
    return result


def safe_dict(val):
    """
    Convert the given value to a dictionary or empyt dict.
    """
    result = {}
    try:
        result = json.loads(val)
    except (ValueError, TypeError):
        pass
    return json.dumps(result)


def get_column_converters(provider_type, **kwargs):
    """
    Get the column data types for a provider.

    Args:
        provider_type (str): The provider type
        kwargs (Dict): Additional meta data related to the report

    Returns:
        (Dict): column_name -> function
    """
    converters = {}
    if provider_type in [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]:
        converters = {
            "bill/BillingPeriodStartDate": pd.to_datetime,
            "bill/BillingPeriodEndDate": pd.to_datetime,
            "lineItem/UsageStartDate": pd.to_datetime,
            "lineItem/UsageEndDate": pd.to_datetime,
            "lineItem/UsageAmount": safe_float,
            "lineItem/NormalizationFactor": safe_float,
            "lineItem/NormalizedUsageAmount": safe_float,
            "lineItem/UnblendedRate": safe_float,
            "lineItem/UnblendedCost": safe_float,
            "lineItem/BlendedRate": safe_float,
            "lineItem/BlendedCost": safe_float,
            "pricing/publicOnDemandCost": safe_float,
            "pricing/publicOnDemandRate": safe_float,
        }
    elif provider_type in [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL]:
        converters = {
            "UsageDateTime": pd.to_datetime,
            "UsageQuantity": safe_float,
            "ResourceRate": safe_float,
            "PreTaxCost": safe_float,
            "Tags": safe_dict,
        }
    elif provider_type == Provider.PROVIDER_OCP:
        converters = {
            "report_period_start": process_openshift_datetime,
            "report_period_end": process_openshift_datetime,
            "interval_start": process_openshift_datetime,
            "interval_end": process_openshift_datetime,
            "node_labels": process_openshift_labels,
            "pod_usage_cpu_core_seconds": safe_float,
            "pod_request_cpu_core_seconds": safe_float,
            "pod_limit_cpu_core_seconds": safe_float,
            "pod_usage_memory_byte_seconds": safe_float,
            "pod_request_memory_byte_seconds": safe_float,
            "pod_limit_memory_byte_seconds": safe_float,
            "node_capacity_cpu_cores": safe_float,
            "node_capacity_cpu_core_seconds": safe_float,
            "node_capacity_memory_bytes": safe_float,
            "node_capacity_memory_byte_seconds": safe_float,
            "pod_labels": process_openshift_labels,
            "persistentvolumeclaim_capacity_bytes": safe_float,
            "persistentvolumeclaim_capacity_byte_seconds": safe_float,
            "volume_request_storage_byte_seconds": safe_float,
            "persistentvolumeclaim_usage_byte_seconds": safe_float,
            "persistentvolume_labels": process_openshift_labels,
            "persistentvolumeclaim_labels": process_openshift_labels,
        }
    return converters


class NamedTemporaryGZip:
    """Context manager for a temporary GZip file.

    Example:
        with NamedTemporaryGZip() as temp_tz:
            temp_tz.read()
            temp_tz.write()

    """

    def __init__(self):
        """Generate a random temporary file name."""
        self.file_name = f"{gettempdir()}/{uuid4()}.gz"

    def __enter__(self):
        """Open a gz file as a fileobject."""
        self.file = gzip.open(self.file_name, "wt")
        return self.file

    def __exit__(self, *exc):
        """Remove the temp file from disk."""
        self.file.close()
        remove(self.file_name)


def dictify_table_export_settings(table_export_settings):
    """Return a dict representation of a table_export_settings named tuple."""
    return {
        "provider": table_export_settings.provider,
        "output_name": table_export_settings.output_name,
        "iterate_daily": table_export_settings.iterate_daily,
        "sql": table_export_settings.sql,
    }


def date_range(start_date, end_date, step=5):
    """Create a range generator for dates.

    Given a start date and end date make an generator that returns the next date
    in the range with the given interval.

    """
    if isinstance(start_date, str):
        start_date = parser.parse(start_date)
    if isinstance(end_date, str):
        end_date = parser.parse(end_date)

    dates = rrule(freq=DAILY, dtstart=start_date, until=end_date, interval=step)

    for date in dates:
        yield date.date()
    if end_date not in dates:
        yield end_date.date()


def date_range_pair(start_date, end_date, step=5):
    """Create a range generator for dates.

    Given a start date and end date make an generator that returns a start
    and end date over the interval.

    """
    if isinstance(start_date, str):
        start_date = parser.parse(start_date)
    if isinstance(end_date, str):
        end_date = parser.parse(end_date)
    dates = list(rrule(freq=DAILY, dtstart=start_date, until=end_date, interval=step))
    # Special case with only 1 period
    if len(dates) == 1:
        yield start_date.date(), end_date.date()
    for date in dates:
        if date == start_date:
            continue
        yield start_date.date(), date.date()
        start_date = date + timedelta(days=1)
    if len(dates) != 1 and end_date not in dates:
        yield start_date.date(), end_date.date()


def get_path_prefix(account, provider_uuid, start_date, data_type):
    """
    Get the S3 bucket prefix
    """
    path = None
    if start_date:
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        path_prefix = f"{Config.WAREHOUSE_PATH}/{data_type}"
        path = f"{path_prefix}/{account}/{provider_uuid}/{year}/{month}"
    return path
