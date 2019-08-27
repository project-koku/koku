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
import calendar
import datetime
import logging
import re

from tenant_schemas.utils import schema_context

from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external import AZURE

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
    local_file_name = cur_key.split('/')[-1]

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
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.replace(day=1)
        start_date = start_date.strftime('%Y-%m-%d')

    if isinstance(end_date, datetime.datetime):
        end_date = end_date.strftime('%Y-%m-%d')

    with ReportingCommonDBAccessor() as reporting_common:
        column_map = reporting_common.column_map

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider = provider_accessor.get_provider()

    if provider.type not in (AZURE,):
        err_msg = 'Provider UUID is not an Azure type.  It is {}'.format(provider.type)
        LOG.warning(err_msg)
        return []

    with AzureReportDBAccessor(schema, column_map) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.id)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            bills = bills.all()

    return bills
