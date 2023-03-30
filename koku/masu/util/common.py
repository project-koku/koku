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
from uuid import uuid4

from dateutil import parser
from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from pytz import UTC
from tenant_schemas.utils import schema_context

import koku.trino_database as trino_db
from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.external import LISTEN_INGEST
from masu.external import POLL_INGEST

LOG = logging.getLogger(__name__)

CSV_REQUIRED_COLUMNS = {
    "AWS": (
        "bill/BillingEntity",
        "bill/BillType",
        "bill/PayerAccountId",
        "bill/BillingPeriodStartDate",
        "bill/BillingPeriodEndDate",
        "bill/InvoiceId",
        "lineItem/LineItemType",
        "lineItem/UsageAccountId",
        "lineItem/UsageStartDate",
        "lineItem/UsageEndDate",
        "lineItem/ProductCode",
        "lineItem/UsageType",
        "lineItem/Operation",
        "lineItem/AvailabilityZone",
        "lineItem/ResourceId",
        "lineItem/UsageAmount",
        "lineItem/NormalizationFactor",
        "lineItem/NormalizedUsageAmount",
        "lineItem/CurrencyCode",
        "lineItem/UnblendedRate",
        "lineItem/UnblendedCost",
        "lineItem/BlendedRate",
        "lineItem/BlendedCost",
        "savingsPlan/SavingsPlanEffectiveCost",
        "lineItem/TaxType",
        "pricing/publicOnDemandCost",
        "pricing/publicOnDemandRate",
        "reservation/AmortizedUpfrontFeeForBillingPeriod",
        "reservation/AmortizedUpfrontCostForUsage",
        "reservation/RecurringFeeForUsage",
        "reservation/UnusedQuantity",
        "reservation/UnusedRecurringFee",
        "pricing/term",
        "pricing/unit",
        "product/sku",
        "product/ProductName",
        "product/productFamily",
        "product/servicecode",
        "product/region",
        "product/instanceType",
        "product/memory",
        "product/vcpu",
        "reservation/ReservationARN",
        "reservation/NumberOfReservations",
        "reservation/UnitsPerReservation",
        "reservation/StartTime",
        "reservation/EndTime",
    ),
    "AWS-custom": (
        "bill_billing_entity",
        "bill_bill_type",
        "bill_payer_account_id",
        "bill_billing_period_start_date",
        "bill_billing_period_end_date",
        "bill_invoice_id",
        "line_item_line_item_type",
        "line_item_usage_account_id",
        "line_item_usage_start_date",
        "line_item_usage_end_date",
        "line_item_product_code",
        "line_item_usage_type",
        "line_item_operation",
        "line_item_availability_zone",
        "line_item_resource_id",
        "line_item_usage_amount",
        "line_item_normalization_factor",
        "line_item_normalized_usage_amount",
        "line_item_currency_code",
        "line_item_unblended_rate",
        "line_item_unblended_cost",
        "line_item_blended_rate",
        "line_item_blended_cost",
        "savings_plan_savings_plan_effective_cost",
        "line_item_tax_type",
        "pricing_public_on_demand_cost",
        "pricing_public_on_demand_rate",
        "reservation_amortized_upfront_fee_for_billing_period",
        "reservation_amortized_upfront_cost_for_usage",
        "reservation_recurring_fee_for_usage",
        "reservation_unused_quantity",
        "reservation_unused_recurring_fee",
        "pricing_term",
        "pricing_unit",
        "product_sku",
        "product_product_name",
        "product_product_family",
        "product_servicecode",
        "product_region",
        "product_instance_type",
        "product_memory",
        "product_vcpu",
        "reservation_number_of_reservations",
        "reservation_units_per_reservation",
        "reservation_start_time",
        "reservation_end_time",
    ),
    "Azure": (
        "SubscriptionGuid",
        "ResourceGroup",
        "ResourceLocation",
        "UsageDateTime",
        "MeterCategory",
        "MeterSubcategory",
        "MeterId",
        "MeterName",
        "MeterRegion",
        "UsageQuantity",
        "ResourceRate",
        "PreTaxCost",
        "ConsumedService",
        "ResourceType",
        "InstanceId",
        "Tags",
        "OfferId",
        "AdditionalInfo",
        "ServiceInfo1",
        "ServiceInfo2",
        "ServiceName",
        "ServiceTier",
        "Currency",
        "UnitOfMeasure",
    ),
    "GCP": (
        "billing_account_id",
        "service.id",
        "service.description",
        "sku.id",
        "sku.description",
        "usage_start_time",
        "usage_end_time",
        "project.id",
        "project.name",
        "project.labels",
        "project.ancestry_numbers",
        "labels",
        "system_labels",
        "location.location",
        "location.country",
        "location.region",
        "location.zone",
        "export_time",
        "cost",
        "currency",
        "currency_conversion_rate",
        "usage.amount",
        "usage.unit",
        "usage.amount_in_pricing_units",
        "usage.pricing_unit",
        "credits",
        "invoice.month",
        "cost_type",
        "partition_date",
    ),
}


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
        Provider.PROVIDER_GCP_LOCAL: POLL_INGEST,
        Provider.PROVIDER_IBM: POLL_INGEST,
        Provider.PROVIDER_IBM_LOCAL: POLL_INGEST,
        Provider.PROVIDER_OCI: POLL_INGEST,
        Provider.PROVIDER_OCI_LOCAL: POLL_INGEST,
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
        start_date = datetime.datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC)
    if isinstance(end_date, str):
        end_date = parser.parse(end_date)
    elif isinstance(end_date, datetime.date):
        end_date = datetime.datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC)

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


def create_enabled_keys(schema, enabled_keys_model, enabled_keys):
    LOG.info("Creating enabled tag key records")
    changed = False

    if enabled_keys:
        with schema_context(schema):
            new_keys = list(set(enabled_keys) - {k.key for k in enabled_keys_model.objects.all()})
            if new_keys:
                changed = True
                # Processing in batches for increased efficiency
                for batch_num, new_batch in enumerate(batch(new_keys, _slice=500)):
                    batch_size = len(new_batch)
                    LOG.info(f"Create batch {batch_num + 1}: batch_size {batch_size}")
                    for ix in range(batch_size):
                        new_batch[ix] = enabled_keys_model(key=new_batch[ix])
                    enabled_keys_model.objects.bulk_create(new_batch, ignore_conflicts=True)

    if not changed:
        LOG.info("No enabled keys added.")

    return changed


def update_enabled_keys(schema, enabled_keys_model, enabled_keys):
    LOG.info("Updating enabled tag keys records")
    changed = False

    enabled_keys_set = set(enabled_keys)
    update_keys_enabled = []
    update_keys_disabled = []

    with schema_context(schema):
        for key in enabled_keys_model.objects.all():
            if key.key in enabled_keys_set:
                if not key.enabled:
                    update_keys_enabled.append(key.key)
            else:
                update_keys_disabled.append(key.key)

        # When we are in create mode, we do not want to change the state of existing keys
        if update_keys_enabled or update_keys_disabled:
            changed = True
            if update_keys_enabled:
                LOG.info(f"Updating {len(update_keys_enabled)} keys to ENABLED")
                enabled_keys_model.objects.filter(key__in=update_keys_enabled).update(enabled=True)

            if update_keys_disabled:
                LOG.info(f"Updating {len(update_keys_disabled)} keys to DISABLED")
                enabled_keys_model.objects.filter(key__in=update_keys_disabled).update(enabled=False)

    if not changed:
        LOG.info("No enabled keys updated.")

    return changed


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
    LOG.info(f"Checking for Trino table {schema_name}.{table_name}")
    table_check_sql = f"SHOW TABLES LIKE '{table_name}'"
    table, _ = execute_trino_query(schema_name, table_check_sql)
    return bool(table)


def convert_account(account):
    """Process the account string for Unleash checks."""
    if account and not account.startswith("acct") and not account.startswith("org"):
        account = f"acct{account}"
    return account


def filter_dictionary(dictionary, keys_to_keep):
    """Filter a dictionary to only include the keys specified."""
    return {key: value for key, value in dictionary.items() if key in keys_to_keep}
