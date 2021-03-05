#
# Copyright 2019 Red Hat, Inc.
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
import datetime
import json
import logging
import re

import ciso8601
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from reporting.provider.azure.models import PRESTO_COLUMNS

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


def get_local_file_name(cur_key):
    """
    Return the local file name for a given cost usage report key.

    If an assemblyID is present in the key, it will prepend it to the filename.

    Args:
        cur_key (String): reportKey value from manifest file.
        example:
        With AssemblyID: /koku/20180701-20180801/882083b7-ea62-4aab-aa6a-f0d08d65ee2b/koku-1.csv.gz
        Without AssemblyID: /koku/20180701-20180801/koku-Manifest.json

    Returns:
        (String): file name for the local file,
                example:
                With AssemblyID: "882083b7-ea62-4aab-aa6a-f0d08d65ee2b-koku-1.csv.gz"
                Without AssemblyID: "koku-Manifest.json"

    """
    local_file_name = cur_key.split("/")[-1]

    return local_file_name


def get_bills_from_provider(provider_uuid, schema, start_date=None, end_date=None):
    """
    Return the Azure bill IDs given a provider UUID.

    Args:
        provider_uuid (str): Provider UUID.
        schema (str): Tenant schema
        start_date (datetime): Start date for bill IDs.
        end_date (datetime) End date for bill IDs.

    Returns:
        (list): Azure cost entry bill objects.

    """
    if isinstance(start_date, (datetime.datetime, datetime.date)):
        start_date = start_date.replace(day=1)
        start_date = start_date.strftime("%Y-%m-%d")

    if isinstance(end_date, (datetime.datetime, datetime.date)):
        end_date = end_date.strftime("%Y-%m-%d")

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider = provider_accessor.get_provider()

    if provider.type not in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
        err_msg = f"Provider UUID is not an Azure type.  It is {provider.type}"
        LOG.warning(err_msg)
        return []

    with AzureReportDBAccessor(schema) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            bills = bills.all()

    return bills


def azure_date_converter(date):
    """Convert Azure date fields properly."""
    try:
        new_date = ciso8601.parse_datetime(date)
    except ValueError:
        date_split = date.split("/")
        new_date_str = date_split[2] + date_split[0] + date_split[1]
        new_date = ciso8601.parse_datetime(new_date_str)
    return new_date


def azure_json_converter(tag_str):
    """Convert either Azure JSON field format to proper JSON."""
    tag_dict = {}
    try:
        if "{" in tag_str:
            tag_dict = json.loads(tag_str)
        else:
            tags = tag_str.split('","')
            for tag in tags:
                key, value = tag.split(": ")
                tag_dict[key.strip('"')] = value.strip('"')
    except (ValueError, TypeError):
        pass

    return json.dumps(tag_dict)


def azure_post_processor(data_frame):
    """Guarantee column order for Azure parquet files"""
    columns = list(data_frame)
    if "MeterSubcategory" in columns:
        data_frame["MeterSubCategory"] = data_frame["MeterSubcategory"]
        data_frame = data_frame.drop(columns=["MeterSubcategory"])
    return data_frame.reindex(columns=PRESTO_COLUMNS)
