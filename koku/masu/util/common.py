#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import calendar
import datetime
import gzip
import json
import logging
import re
from datetime import timedelta
from itertools import groupby
from os import remove
from tempfile import gettempdir
from threading import RLock
from uuid import uuid4

import pandas as pd
from dateutil import parser
from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from django.conf import settings
from django_tenants.utils import schema_context

import koku.trino_database as trino_db
from api.common import log_json
from api.utils import DateHelper
from koku.reportdb_accessor import get_report_db_accessor
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from reporting.provider.all.models import EnabledTagKeys
from reporting_common.models import CostUsageReportManifest
from reporting_common.states import ManifestStep

LOG = logging.getLogger(__name__)


class CreateDailyArchivesError(Exception):
    """Unable to create daily archives."""


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
    return f"{start_month.strftime(timeformat)}-{end_month.strftime(timeformat)}"


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


def strip_characters_from_column_name(column_name):
    """Return a valid Hive/Trino column name."""
    return re.sub(r"\W+", "_", column_name).lower()


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
    elif isinstance(start_date, datetime.date):
        start_date = datetime.datetime(start_date.year, start_date.month, start_date.day, tzinfo=settings.UTC)
    if isinstance(end_date, str):
        end_date = parser.parse(end_date)
    elif isinstance(end_date, datetime.date):
        end_date = datetime.datetime(end_date.year, end_date.month, end_date.day, tzinfo=settings.UTC)

    dates = list(rrule(freq=DAILY, dtstart=start_date, until=end_date, interval=step))
    # Special case with only 1 period
    if len(dates) == 1:
        yield start_date.date(), end_date.date()
    else:
        for date in dates:
            if date == start_date and date != end_date:
                continue
            yield start_date.date(), date.date()
            start_date = date + timedelta(days=1)
        if len(dates) != 1 and end_date not in dates:
            yield start_date.date(), end_date.date()


def get_path_prefix(
    account, provider_type, provider_uuid, start_date, data_type, report_type=None, daily=False, partition_daily=False
):
    """Get the S3 bucket prefix"""
    path = None
    if start_date:
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        day = start_date.strftime("%d")
        path_prefix = f"{Config.WAREHOUSE_PATH}/{data_type}"
        if daily:
            path_prefix += "/daily"
        path = f"{path_prefix}/{account}/{provider_type}/source={provider_uuid}/year={year}/month={month}"
        if report_type:
            path = (
                f"{path_prefix}/{account}/{provider_type}/{report_type}"
                f"/source={provider_uuid}/year={year}/month={month}"
            )
        if partition_daily:
            path += f"/day={day}"
    return path


def get_hive_table_path(account, provider_type, report_type=None, daily=False):
    """Get the S3 bucket prefix without partitions for hive table location."""
    path_prefix = f"{Config.WAREHOUSE_PATH}/{Config.PARQUET_DATA_TYPE}"
    if daily:
        path_prefix += "/daily"
        if report_type is None:
            report_type = "raw"
    table_path = f"{path_prefix}/{account}/{provider_type}"
    if report_type:
        table_path += f"/{report_type}"
    return table_path


def determine_if_full_summary_update_needed(bill):
    """Decide whether to update summary tables for full billing period."""
    now_utc = DateHelper().now_utc
    is_new_bill = bill.summary_data_creation_datetime is None
    is_current_month = False
    if hasattr(bill, "billing_period_start"):
        is_current_month = (
            bill.billing_period_start.year == now_utc.year and bill.billing_period_start.month == now_utc.month
        )
    elif hasattr(bill, "report_period_start"):
        is_current_month = (
            bill.report_period_start.year == now_utc.year and bill.report_period_start.month == now_utc.month
        )

    # Do a full month update if this is the first time we've seen the current month's data
    # or if it is from a previous month
    return is_new_bill or not is_current_month


def split_alphanumeric_string(s):
    for k, g in groupby(s, str.isalpha):
        yield "".join(g)


def batch(iterable, start=0, stop=None, _slice=1):
    iterable = list(iterable) if not isinstance(iterable, list) else iterable
    length = len(iterable)
    if stop is None:
        stop = length
    else:
        stop = int(stop)
    if stop < 0:
        stop = length + stop
    if stop > length:
        stop = length
    if start is None:
        start = 0
    else:
        start = int(start)
    if start < 0:
        start = length + start

    while start < stop:
        end = start + _slice
        res = iterable[start:end]
        start = end
        yield res


def populate_enabled_tag_rows_with_false(schema: str, tags: set[str, ...], provider_type: str) -> None:
    """
    Creates enabled tag records always as false.
    """
    ctx = {"schema": schema, "tags": tags, "provider_type": provider_type}
    LOG.info(log_json(msg="checking tag enabled population with false", context=ctx))
    if not tags:
        LOG.info(log_json(msg="skipping tag enablement no tags found", context=ctx))
        return

    with schema_context(schema):
        new_tags = tags.difference(
            k for k in EnabledTagKeys.objects.filter(provider_type=provider_type).values_list("key", flat=True)
        )
        if not new_tags:
            LOG.info(log_json(msg="skipping tag enablement no new tags found", context=ctx))
            return
        for batch_num, new_batch in enumerate(batch(new_tags, _slice=500)):
            batch_size = len(new_batch)
            LOG.info(
                log_json(
                    msg="create tag batch with false", batch_number=(batch_num + 1), batch_size=batch_size, context=ctx
                )
            )
            new_records = [EnabledTagKeys(key=key, provider_type=provider_type, enabled=False) for key in new_batch]
            EnabledTagKeys.objects.bulk_create(new_records, ignore_conflicts=True)


def populate_enabled_tag_rows_with_limit(schema: str, tags: set[str, ...], provider_type: str) -> None:
    """
    Creates enabled tag records checking limit.
    """
    ctx = {"schema": schema, "tags": tags, "provider_type": provider_type}
    LOG.info(log_json(msg="checking tag enabled population with limit", context=ctx))
    if not tags:
        LOG.info(log_json(msg="skipping tag enablement no tags found", context=ctx))
        return

    with schema_context(schema):
        new_tags = tags.difference(
            k for k in EnabledTagKeys.objects.filter(provider_type=provider_type).values_list("key", flat=True)
        )
        if not new_tags:
            LOG.info(log_json(msg="skipping tag enablement no new tags found", context=ctx))
            return

        if Config.ENABLED_TAG_LIMIT > 0:
            # Early check if limit is enabled to grab enabled tag count once and only once
            enabled_tag_count = EnabledTagKeys.objects.filter(enabled=True).count()
            delta_to_limit = max((Config.ENABLED_TAG_LIMIT - enabled_tag_count), 0)
            ctx["enabled_tag_limit"] = Config.ENABLED_TAG_LIMIT
            ctx["delta_to_limit"] = delta_to_limit

        for batch_num, new_batch in enumerate(batch(new_tags, _slice=500)):
            batch_size = len(new_batch)
            LOG.info(
                log_json(
                    msg="create tag batch with limit", batch_number=(batch_num + 1), batch_size=batch_size, context=ctx
                )
            )
            if Config.ENABLED_TAG_LIMIT > 0:
                new_records = [
                    EnabledTagKeys(key=key, provider_type=provider_type, enabled=True)
                    for key in new_batch[:delta_to_limit]
                ]
                enabled_records_count = len(new_records)
                # disable records past our limit
                new_records.extend(
                    EnabledTagKeys(key=key, provider_type=provider_type, enabled=False)
                    for key in new_batch[delta_to_limit:]
                )
                # update delta for next batch
                delta_to_limit -= enabled_records_count
                ctx["delta_to_limit"] = delta_to_limit
            else:
                # tag limit is disabled or default is False
                new_records = (EnabledTagKeys(key=key, provider_type=provider_type, enabled=True) for key in new_batch)
            EnabledTagKeys.objects.bulk_create(new_records, ignore_conflicts=True)


def execute_trino_query(schema_name, sql, params=None):
    """Execute Trino SQL."""
    connection = trino_db.connect(schema=schema_name)
    cur = connection.cursor()
    cur.execute(sql, params=params)
    results = cur.fetchall()
    if cur.description is None:
        columns = []
    else:
        columns = [col[0] for col in cur.description]
    return results, columns


def trino_table_exists(schema_name, table_name):
    """Given a schema and table name, check for an existing table in Trino."""

    LOG.info(log_json(msg="checking for Trino table", schema=schema_name, table=table_name))
    table_check_sql = get_report_db_accessor().get_table_check_sql(table_name, schema_name)
    table, _ = execute_trino_query(schema_name, table_check_sql)
    return bool(table)


def source_in_trino_table(schema_name, source_uuid, table_name):
    """Checks to see if source is in trino table, but first checks
    to see if trino table exists.

    Returns:
        int: The count of partitions for the source in the table, or 0 if table doesn't exist.
    """
    if trino_table_exists(schema_name, table_name):
        source_has_partitions = get_report_db_accessor().get_check_source_in_partitions_sql(
            schema_name, table_name, source_uuid
        )
        results, _ = execute_trino_query(schema_name, source_has_partitions)
        return results[0][0] if results else 0
    return 0


def convert_account(account):
    """Process the account string for Unleash checks."""
    if account and not account.startswith("acct") and not account.startswith("org"):
        account = f"acct{account}"
    return account


def filter_dictionary(dictionary, keys_to_keep):
    """Filter a dictionary to only include the keys specified."""
    return {key: value for key, value in dictionary.items() if key in keys_to_keep}


class SingletonMeta(type):
    """
    This is a thread-safe implementation of Singleton.
    """

    _instances = {}
    _lock: RLock = RLock()

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        with cls._lock:
            # The first thread to acquire the lock, reaches this conditional,
            # goes inside and creates the Singleton instance. Once it leaves the
            # lock block, a thread that might have been waiting for the lock
            # release may then enter this section. But since the Singleton field
            # is already initialized, the thread won't create a new object.
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]


def fetch_optional_columns(local_file, current_columns, fetch_columns, tracing_id, context):
    """Add optional columns to columns list if they exists in files"""
    for fetch_column in fetch_columns:
        try:
            data_frame = pd.read_csv(
                local_file, usecols=lambda col: col.lower().startswith(fetch_column.lower()), nrows=0
            )
            header_chunks = chunk_columns(data_frame.columns, settings.PANDAS_COLUMN_BATCH_SIZE)
            # Chunk out the headers for excessive tag git statcolumn counts
            for header_chunk in header_chunks:
                data_frame = pd.read_csv(local_file, usecols=header_chunk)
                data_frame = data_frame.dropna(axis=1, how="all")
                fetch_cols = data_frame.columns
                for col in fetch_cols:
                    current_columns.add(col)
        except ValueError:
            LOG.info(log_json(tracing_id, msg=f"customer has no {fetch_column} data to parse", context=context))
    return current_columns


def chunk_columns(col_list, chunk_count):
    for i in range(0, len(col_list), chunk_count):
        yield list(col_list[i : i + chunk_count])


def set_summary_timestamp(state, manifest_id):
    """Function for setting last summary for given manifest"""
    if manifest_id:
        LOG.info(f"setting summary {state} for manifest: {manifest_id}")
        ReportManifestDBAccessor().update_manifest_state(ManifestStep.SUMMARY, state, manifest_id)


def get_latest_openshift_on_cloud_manifest(start_date, provider_uuid):
    """Function for getting latest manifest for given openshift provider (ocp on cloud)"""
    start_date = parser.parse(str(start_date))
    manifest_id = None
    # We need to update previous manifests for customer filtered flows
    billing_period = DateHelper().month_start_utc(start_date)
    if provider_uuid:
        try:
            manifest = CostUsageReportManifest.objects.filter(
                provider=provider_uuid,
                billing_period_start_datetime=billing_period,
                creation_datetime__isnull=False,
            ).latest("creation_datetime")
            manifest_id = manifest.id
        except CostUsageReportManifest.DoesNotExist:
            pass
    return manifest_id
