#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS utility functions."""
import contextlib
import datetime
import logging
import math
import re
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import IntegrityError
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.util import common as utils
from masu.util.common import get_path_prefix
from reporting.models import AWSAccountAlias
from reporting.models import AWSCostEntryBill

LOG = logging.getLogger(__name__)


RECOMMENDED_COLUMNS = {
    "bill/BillingEntity",
    "bill/BillType",
    "bill/PayerAccountId",
    "bill/BillingPeriodStartDate",
    "bill/BillingPeriodEndDate",
    "bill/InvoiceId",
    "identity/TimeInterval",
    "lineItem/LineItemType",
    "lineItem/LegalEntity",
    "lineItem/LineItemDescription",
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
    "reservation/NumberOfReservations",
    "reservation/UnitsPerReservation",
    "reservation/StartTime",
    "reservation/EndTime",
}

RECOMMENDED_ALT_COLUMNS = {
    "bill_billing_entity",
    "bill_bill_type",
    "bill_payer_account_id",
    "bill_billing_period_start_date",
    "bill_billing_period_end_date",
    "bill_invoice_id",
    "identity_time_interval",
    "line_item_legal_entity",
    "line_item_line_item_description",
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
    "reservation_number_of_reservations",
    "reservation_units_per_reservation",
    "reservation_start_time",
    "reservation_end_time",
}

OPTIONAL_COLS = {
    "product/physicalCores",
    "product/instanceType",
    "product/vcpu",
    "product/memory",
    "product/operatingSystem",
}

OPTIONAL_ALT_COLS = {
    "product_physical_cores",
    "product_instancetype",
    "product_vcpu",
    "product_memory",
    "product_operating_system",
}

DATE_FMT = "%Y-%m-%d"

# pylint: disable=too-few-public-methods


class UploadError(Exception):
    """Unable to upload to S3."""


class AwsArn:
    """
    Object representing an AWS ARN.

    See also:
        https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html

    General ARN formats:
        arn:partition:service:region:account-id:resource
        arn:partition:service:region:account-id:resourcetype/resource
        arn:partition:service:region:account-id:resourcetype:resource

    Example ARNs:
        <!-- Elastic Beanstalk application version -->
        arn:aws:elasticbeanstalk:us-east-1:123456789012:environment/My App/foo
        <!-- IAM user name -->
        arn:aws:iam::123456789012:user/David
        <!-- Amazon RDS instance used for tagging -->
        arn:aws:rds:eu-west-1:123456789012:db:mysql-db
        <!-- Object in an Amazon S3 bucket -->
        arn:aws:s3:::my_corporate_bucket/exampleobject.png

    """

    arn_regex = re.compile(
        r"^arn:(?P<partition>\w+):(?P<service>\w+):"
        r"(?P<region>\w+(?:-\w+)+)?:"
        r"(?P<account_id>\d{12})?:(?P<resource_type>[^:/]+)"
        r"(?P<resource_separator>[:/])?(?P<resource>.*)"
    )

    partition = None
    service = None
    region = None
    account_id = None
    resource_type = None
    resource_separator = None
    resource = None

    def __init__(self, credentials):
        """
        Parse ARN string into its component pieces.

        Args:
            credentials (Dict): Amazon Resource Name + External ID in credentials

        """
        match = False
        self.arn = credentials.get("role_arn")
        self.external_id = credentials.get("external_id")
        if self.arn:
            match = self.arn_regex.match(self.arn)

        if match:
            for key, val in match.groupdict().items():
                setattr(self, key, val)
        else:
            LOG.warning(f"Invalid ARN: {self.arn}")

    def __repr__(self):
        """Return the ARN itself."""
        return self.arn


def get_assume_role_session(
    arn: AwsArn, session: str = "MasuSession", region_name: str = "us-east-1"
) -> boto3.session.Session:
    """
    Assume a Role and obtain session credentials for the given role.

    Args:
        arn (AwsArn): Amazon Resource Name
        session (String): A session name

    Usage :
        session = get_assume_role_session(session='ExampleSessionName',
                                          arn='arn:aws:iam::012345678901:role/my-role')
        client = session.client('sqs')

    See: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html

    """
    client = boto3.client("sts", region_name=region_name)
    assume_role_kwargs = {"RoleArn": str(arn), "RoleSessionName": session}
    if arn.external_id:
        assume_role_kwargs["ExternalId"] = arn.external_id
    response = client.assume_role(**assume_role_kwargs)
    return boto3.Session(
        aws_access_key_id=response["Credentials"]["AccessKeyId"],
        aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
        aws_session_token=response["Credentials"]["SessionToken"],
        region_name=region_name,
    )


def get_available_regions(service_name: str = "ec2") -> list[str]:
    """
    Return a list of available regions for the given service.

    This list is not comprehensive as it comes from the internal boto3 library
    and does not query AWS directly.

    Args:
        service_name: Amazon service name

    Usage:
        regions = get_available_regions("s3")

    See:https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html#boto3.session.Session.get_available_regions

    """

    session = boto3.Session()
    return session.get_available_regions(service_name)


def get_cur_report_definitions(cur_client, role_arn=None, retries=7, max_wait_time=10):
    """
    Get Cost Usage Reports associated with a given RoleARN.

    Args:
        role_arn      (str) RoleARN for AWS session
        retries       (int) Number of times to retry if the connection fails
        max_wait_time (int) Max amount of time to wait between retries

    """
    if role_arn:
        session = get_assume_role_session(role_arn)
        cur_client = session.client("cur", region_name="us-east-1")
    for i in range(retries):  # Common retry logic added because AWS is randomly dropping connections
        try:
            defs = cur_client.describe_report_definitions()
            return defs
        except ClientError:
            if i < (retries - 1):
                delay = min(2**i, max_wait_time)
                LOG.info(
                    "AWS client error while describing report definitions. "
                    f"Attempt {i + 1} of {retries}. Retrying in {delay}s..."
                )
                time.sleep(delay)
                continue
            else:
                raise


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
    start_month = for_date_time
    if isinstance(start_month, datetime.datetime):
        start_month = start_month.date()
    start_month = start_month.replace(day=1)
    end_month = start_month + relativedelta(months=+1)
    timeformat = "%Y%m%d"
    return f"{start_month.strftime(timeformat)}-{end_month.strftime(timeformat)}"


def get_assembly_id_from_cur_key(key):
    """
    Get the assembly ID from a cost and usage report key.

    Args:
        key (String): Full key for a cost and usage report location.
        example: /koku/20180701-20180801/882083b7-ea62-4aab-aa6a-f0d08d65ee2b/koku-1.csv.gz

    Returns:
        (String): "Assembly ID UUID"
        example: "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"

    """
    assembly_id = utils.extract_uuids_from_string(key)
    assembly_id = assembly_id.pop() if assembly_id else None

    return assembly_id


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
    s3_filename = cur_key.split("/")[-1]
    assembly_id = get_assembly_id_from_cur_key(cur_key)
    local_file_name = f"{assembly_id}-{s3_filename}" if assembly_id else f"{s3_filename}"

    return local_file_name


def get_account_alias_from_role_arn(arn: AwsArn, provider: Provider, session: boto3.session.Session = None):
    """
    Get account ID for given RoleARN.

    Args:
        arn     (AwsArn) AWS IAM RoleARN object

    Returns:
        (String): Account ID

    """
    context_key = "aws_list_account_aliases"
    if not session:
        session = get_assume_role_session(arn)
    iam_client = session.client("iam")

    account_id = arn.arn.split(":")[-2]
    alias = account_id

    context = provider.additional_context or {}
    if context.get(context_key, True):
        try:
            alias_response = iam_client.list_account_aliases()
            alias_list = alias_response.get("AccountAliases", [])
            # Note: Boto3 docs states that you can only have one alias per account
            # so the pop() should be ok...
            alias = alias_list.pop() if alias_list else None
        except ClientError as err:
            LOG.info("Unable to list account aliases.  Reason: %s", str(err))
            context[context_key] = False
            provider.set_additional_context(context)

    return (account_id, alias)


def get_account_names_by_organization(arn: AwsArn, provider: Provider, session: boto3.session.Session = None):
    """
    Get account ID for given RoleARN.

    Args:
        arn     (AwsArn) AWS IAM RoleARN + External ID object

    Returns:
        (list): Dictionaries of accounts with id, name keys

    """
    context_key = "crawl_hierarchy"
    if not session:
        session = get_assume_role_session(arn)
    all_accounts = []
    context = provider.additional_context or {}
    if context.get(context_key, True):
        try:
            org_client = session.client("organizations")
            paginator = org_client.get_paginator("list_accounts")
            response_iterator = paginator.paginate()
            for response in response_iterator:
                accounts = response.get("Accounts", [])
                for account in accounts:
                    account_id = account.get("Id")
                    name = account.get("Name")
                    all_accounts.append({"id": account_id, "name": name})
        except ClientError as err:
            LOG.info("Unable to list accounts using organization API.  Reason: %s", str(err))

    return all_accounts


def update_account_aliases(provider: Provider):
    """Update the account aliases."""
    schema = provider.account["schema_name"]
    credentials = provider.account["credentials"]
    _arn = AwsArn(credentials)
    account_id, account_alias = get_account_alias_from_role_arn(_arn, provider)
    with contextlib.suppress(IntegrityError), schema_context(schema):
        AWSAccountAlias.objects.get_or_create(account_id=account_id, account_alias=account_alias)

    accounts = get_account_names_by_organization(_arn, provider)
    for account in accounts:
        acct_id = account.get("id")
        acct_alias = account.get("name")
        if acct_id and acct_alias:
            with contextlib.suppress(IntegrityError), schema_context(schema):
                AWSAccountAlias.objects.get_or_create(account_id=acct_id, account_alias=acct_alias)


def get_bills_from_provider(
    provider_uuid: str,
    schema: str,
    start_date: datetime.datetime | str = None,
    end_date: datetime.datetime | str = None,
) -> list[AWSCostEntryBill]:
    """
    Return the AWS bill IDs given a provider UUID.

    Args:
        provider_uuid (str): Provider UUID.
        schema (str): Tenant schema
        start_date (datetime, str): Start date for bill IDs.
        end_date (datetime, str) End date for bill IDs.

    Returns:
        (list): AWS cost entry bill objects.

    """
    if isinstance(start_date, (datetime.datetime, datetime.date)):
        start_date = start_date.replace(day=1)
        start_date = start_date.strftime(DATE_FMT)

    if isinstance(end_date, (datetime.datetime, datetime.date)):
        end_date = end_date.strftime(DATE_FMT)

    provider = Provider.objects.filter(uuid=provider_uuid).first()
    if not provider:
        err_msg = "Provider UUID is not associated with a given provider."
        LOG.warning(err_msg)
        return []

    if provider.type not in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
        err_msg = f"Provider UUID is not an AWS type.  It is {provider.type}"
        LOG.warning(err_msg)
        return []

    with AWSReportDBAccessor(schema) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            # postgres doesn't always return this query in the same order, ordering by ID (PK) will
            # ensure that any list iteration or indexing is always done in the same order
            bills = list(bills.order_by("id").all())

    return bills


def get_s3_resource(access_key, secret_key, region, endpoint_url=settings.S3_ENDPOINT):  # pragma: no cover
    """
    Obtain the s3 session client
    """
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    aws_session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    return aws_session.resource("s3", endpoint_url=endpoint_url, config=config)


def copy_data_to_s3_bucket(tracing_id, path, filename, data, metadata=None, context=None):
    """
    Copies data to s3 bucket file
    """
    if context is None:
        context = {}
    upload_key = f"{path}/{filename}"
    extra_args = {}
    if metadata:
        extra_args["Metadata"] = metadata
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    s3_obj = {"bucket_name": settings.S3_BUCKET_NAME, "key": upload_key}
    upload = s3_resource.Object(**s3_obj)
    try:
        upload.upload_fileobj(data, ExtraArgs=extra_args)
    except (EndpointConnectionError, ClientError) as err:
        msg = "unable to copy data to bucket"
        LOG.info(log_json(tracing_id, msg=msg, context=context, upload_key=upload_key), exc_info=err)
        raise UploadError(msg)
    return upload


def copy_local_report_file_to_s3_bucket(
    tracing_id, s3_path, full_file_path, local_filename, manifest_id, context=None
):
    """
    Copies local report file to s3 bucket
    """
    if context is None:
        context = {}
    if s3_path:
        LOG.info(f"copy_local_report_file_to_s3_bucket: {s3_path} {full_file_path}")
        metadata = {"manifestid": str(manifest_id)}
        with open(full_file_path, "rb") as fin:
            copy_data_to_s3_bucket(tracing_id, s3_path, local_filename, fin, metadata, context)


def _get_s3_objects(s3_path):
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    return s3_resource.Bucket(settings.S3_BUCKET_NAME).objects.filter(Prefix=s3_path)


def get_or_clear_daily_s3_by_date(csv_s3_path, provider_uuid, start_date, end_date, manifest_id, context, request_id):
    """
    Fetches latest processed date based on daily csv files and clears relevant s3 files
    """
    # We do this if we have multiple workers running different files for a single manifest.
    manifest_accessor = ReportManifestDBAccessor()
    manifest = manifest_accessor.get_manifest_by_id(manifest_id)
    processing_date = manifest_accessor.get_manifest_daily_start_date(manifest_id)
    if processing_date:
        if not manifest_accessor.get_s3_parquet_cleared(manifest):
            # Prevent other works running trino queries until all files are removed.
            clear_s3_files(csv_s3_path, provider_uuid, processing_date, "manifestid", manifest_id, context, request_id)
        return processing_date
    processing_date = start_date
    try:
        s3_date = datetime.date.min
        for obj_summary in _get_s3_objects(csv_s3_path):
            existing_object = obj_summary.Object()
            date_in_filename = datetime.datetime.strptime(
                existing_object.key.split(f"{csv_s3_path}/")[1].split("_")[0], DATE_FMT
            ).date()
            s3_date = max(s3_date, date_in_filename)
        # AWS bills savings plans ahead of time, make sure we dont only process future dates
        if s3_date != datetime.date.min:
            process_date = min(s3_date, end_date)
            processing_date = (
                process_date - datetime.timedelta(days=3) if process_date.day > 3 else process_date.replace(day=1)
            )
            # Set processing date for all workers
            processing_date = manifest_accessor.set_manifest_daily_start_date(manifest_id, processing_date)
        # Try to clear s3 files for dates. Small edge case, we may have parquet files even without csvs
        clear_s3_files(csv_s3_path, provider_uuid, processing_date, "manifestid", manifest_id, context, request_id)
    except (EndpointConnectionError, ClientError, AttributeError, ValueError):
        msg = (
            "unable to fetch date from objects, "
            "attempting to remove csv files and mark manifest to clear parquet files for full month processing"
        )
        LOG.warning(
            log_json(
                request_id,
                msg=msg,
                context=context,
                bucket=settings.S3_BUCKET_NAME,
            ),
        )
        processing_date = manifest_accessor.set_manifest_daily_start_date(manifest_id, processing_date)
        to_delete = get_s3_objects_not_matching_metadata(
            request_id,
            csv_s3_path,
            metadata_key="manifestid",
            metadata_value_check=manifest_id,
            context=context,
        )
        delete_s3_objects(request_id, to_delete, context)
        manifest_accessor.mark_s3_csv_cleared(manifest)
        LOG.info(
            log_json(msg="removed csv files, marked manifest csv cleared and parquet not cleared", context=context)
        )
    return processing_date


def safe_str_int_conversion(value):
    """Convert string to integer safely. If conversion fails or value is empty/None, return None."""
    try:
        return int(value) if value and value.strip() != "" else None
    except ValueError:
        return None


def filter_s3_objects_less_than(
    request_id: str,
    keys: list[str],
    metadata_key: str,
    metadata_value_check: str,
    context: dict | None = None,
) -> list[str]:
    """Filter S3 object keys based on a metadata key integer value comparison.

    Parameters:
    - request_id (str): The ID associated with the request or process.
    - keys (list): A list of S3 object keys to be filtered.
    - metadata_key (str): The metadata key used for the value comparison.
    - metadata_value_check (str): The string value to be converted to an integer for comparison.
    - context (dict, optional): Additional context for logging. Defaults to an empty dict.

    Returns:
    - list: A list of keys.

    Exceptions:
    - Logs both EndpointConnectionError and ClientError exceptions.
    """
    int_metadata_value_check = safe_str_int_conversion(metadata_value_check)
    if int_metadata_value_check is None:
        return []

    if context is None:
        context = {}

    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)

    filtered = []
    for key in keys:
        try:
            obj = s3_resource.Object(settings.S3_BUCKET_NAME, key)
            metadata_value = obj.metadata.get(metadata_key)
            int_metadata_value = safe_str_int_conversion(metadata_value)

            if int_metadata_value is not None and int_metadata_value < int_metadata_value_check:
                filtered.append(key)

        except (EndpointConnectionError, ClientError) as err:
            LOG.warning(
                log_json(
                    request_id,
                    msg="unable to get matching data in bucket",
                    context=context,
                    bucket=settings.S3_BUCKET_NAME,
                ),
                exc_info=err,
            )
            filtered = []

    return filtered


def get_s3_objects_matching_metadata(
    request_id, s3_path, *, metadata_key, metadata_value_check, context=None
) -> list[str]:
    if not s3_path:
        return []
    if context is None:
        context = {}
    try:
        keys = []
        for obj_summary in _get_s3_objects(s3_path):
            existing_object = obj_summary.Object()
            metadata_value = existing_object.metadata.get(metadata_key)
            if metadata_value == metadata_value_check:
                keys.append(existing_object.key)
        return keys
    except (EndpointConnectionError, ClientError) as err:
        LOG.warning(
            log_json(
                request_id,
                msg="unable to get matching data in bucket",
                context=context,
                bucket=settings.S3_BUCKET_NAME,
            ),
            exc_info=err,
        )
    return []


def get_s3_objects_not_matching_metadata(
    request_id, s3_path, *, metadata_key, metadata_value_check, context=None
) -> list[str]:
    if not s3_path:
        return []
    if context is None:
        context = {}
    try:
        keys = []
        for obj_summary in _get_s3_objects(s3_path):
            existing_object = obj_summary.Object()
            metadata_value = existing_object.metadata.get(metadata_key)
            if metadata_value != metadata_value_check:
                keys.append(existing_object.key)
        return keys
    except (EndpointConnectionError, ClientError) as err:
        LOG.warning(
            log_json(
                request_id,
                msg="unable to get non-matching data in bucket",
                context=context,
                bucket=settings.S3_BUCKET_NAME,
            ),
            exc_info=err,
        )
    return []


def delete_s3_objects_matching_metadata(
    request_id, s3_path, *, metadata_key, metadata_value_check, context=None
) -> list[str]:
    keys_to_delete = get_s3_objects_matching_metadata(
        request_id,
        s3_path,
        metadata_key=metadata_key,
        metadata_value_check=metadata_value_check,
        context=context,
    )
    return delete_s3_objects(request_id, keys_to_delete, context)


def delete_s3_objects_not_matching_metadata(
    request_id, s3_path, *, metadata_key, metadata_value_check, context=None
) -> list[str]:
    keys_to_delete = get_s3_objects_not_matching_metadata(
        request_id,
        s3_path,
        metadata_key=metadata_key,
        metadata_value_check=metadata_value_check,
        context=context,
    )
    return delete_s3_objects(request_id, keys_to_delete, context)


def delete_s3_objects(request_id, keys_to_delete, context) -> list[str]:
    keys_to_delete = [{"Key": key} for key in keys_to_delete]
    LOG.info(log_json(request_id, msg="attempting to batch delete s3 files", context=context))
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    s3_bucket = s3_resource.Bucket(settings.S3_BUCKET_NAME)
    try:
        batch_size = 1000  # AWS S3 delete API limits to 1000 objects per request.
        for batch_number in range(math.ceil(len(keys_to_delete) / batch_size)):
            batch_start = batch_size * batch_number
            batch_end = batch_start + batch_size
            object_keys_batch = keys_to_delete[batch_start:batch_end]
            s3_bucket.delete_objects(Delete={"Objects": object_keys_batch})
            LOG.info(
                log_json(
                    request_id,
                    msg="removed batch files from s3 bucket",
                    context=context,
                    bucket=settings.S3_BUCKET_NAME,
                    file_list=object_keys_batch,
                )
            )
        return keys_to_delete
    except (EndpointConnectionError, ClientError) as err:
        LOG.warning(
            log_json(
                request_id, msg="unable to remove data in bucket", context=context, bucket=settings.S3_BUCKET_NAME
            ),
            exc_info=err,
        )
    return []


def clear_s3_files(
    csv_s3_path, provider_uuid, start_date, metadata_key, manifest_id, context, request_id, invoice_month=None
):
    """Clear s3 files for daily archive processing"""
    account = context.get("account")
    # This fixes local providers s3/minio paths for deletes
    provider_type = context.get("provider_type").strip("-local")
    parquet_path_s3 = get_path_prefix(account, provider_type, provider_uuid, start_date, "parquet")
    parquet_daily_path_s3 = get_path_prefix(
        account, provider_type, provider_uuid, start_date, "parquet", report_type="raw", daily=True
    )
    parquet_ocp_on_cloud_path_s3 = get_path_prefix(
        account, provider_type, provider_uuid, start_date, "parquet", report_type="openshift", daily=True
    )
    s3_prefixes = []
    dh = DateHelper()
    list_dates = dh.list_days(start_date, dh.now.date())
    og_path = "/"
    if provider_type == "GCP":
        og_path += f"{invoice_month}_"
        # GCP openshift data is partitioned by day
        day = start_date.strftime("%d")
        parquet_ocp_on_cloud_path_s3 += f"/day={day}"
        list_dates = [start_date.date()]
    for _date in list_dates:
        path = f"{og_path}{_date}"
        s3_prefixes.append(csv_s3_path + path)
        s3_prefixes.append(parquet_path_s3 + path)
        s3_prefixes.append(parquet_daily_path_s3 + path)
        s3_prefixes.append(parquet_ocp_on_cloud_path_s3 + path)
    to_delete = []
    for prefix in s3_prefixes:
        to_delete.extend(
            get_s3_objects_not_matching_metadata(
                request_id, prefix, metadata_key=metadata_key, metadata_value_check=str(manifest_id), context=context
            )
        )
    delete_s3_objects(request_id, to_delete, context)
    manifest_accessor = ReportManifestDBAccessor()
    manifest = manifest_accessor.get_manifest_by_id(manifest_id)
    # Note: Marking the parquet files cleared here prevents all
    # the parquet files for the manifest from being deleted
    # later on in report_parquet_processor
    manifest_accessor.mark_s3_parquet_cleared(manifest)


def remove_files_not_in_set_from_s3_bucket(request_id, s3_path, manifest_id, context=None):
    """
    Removes all files in a given prefix if they are not within the given set.

    This function should be deprecated and replaced with `delete_s3_objects_not_matching_metadata`.
    """
    return delete_s3_objects_not_matching_metadata(
        request_id, s3_path, metadata_key="manifestid", metadata_value_check=manifest_id, context=context
    )
