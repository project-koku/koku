#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS utility functions."""
import datetime
import json
import logging
import re
import uuid
from itertools import chain

import boto3
import ciso8601
import pandas as pd
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from dateutil.relativedelta import relativedelta
from django.conf import settings
from tenant_schemas.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util import common as utils
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from masu.util.ocp.common import match_openshift_labels
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS

LOG = logging.getLogger(__name__)

COL_TRANSLATION = {
    "bill_billing_entity": "bill/BillingEntity",
    "bill_bill_type": "bill/BillType",
    "bill_payer_account_id": "bill/PayerAccountId",
    "bill_billing_period_start_date": "bill/BillingPeriodStartDate",
    "bill_billing_period_end_date": "bill/BillingPeriodEndDate",
    "bill_invoice_id": "bill/InvoiceId",
    "line_item_line_item_type": "lineItem/LineItemType",
    "line_item_usage_account_id": "lineItem/UsageAccountId",
    "line_item_usage_start_date": "lineItem/UsageStartDate",
    "line_item_usage_end_date": "lineItem/UsageEndDate",
    "line_item_product_code": "lineItem/ProductCode",
    "line_item_usage_type": "lineItem/UsageType",
    "line_item_operation": "lineItem/Operation",
    "line_item_availability_zone": "lineItem/AvailabilityZone",
    "line_item_resource_id": "lineItem/ResourceId",
    "line_item_usage_amount": "lineItem/UsageAmount",
    "line_item_normalization_factor": "lineItem/NormalizationFactor",
    "line_item_normalized_usage_amount": "lineItem/NormalizedUsageAmount",
    "line_item_currency_code": "lineItem/CurrencyCode",
    "line_item_unblended_rate": "lineItem/UnblendedRate",
    "line_item_unblended_cost": "lineItem/UnblendedCost",
    "line_item_blended_rate": "lineItem/BlendedRate",
    "line_item_blended_cost": "lineItem/BlendedCost",
    "savings_plan_savings_plan_effective_cost": "savingsPlan/SavingsPlanEffectiveCost",
    "line_item_tax_type": "lineItem/TaxType",
    "pricing_public_on_demand_cost": "pricing/publicOnDemandCost",
    "pricing_public_on_demand_rate": "pricing/publicOnDemandRate",
    "reservation_amortized_upfront_fee_for_billing_period": "reservation/AmortizedUpfrontFeeForBillingPeriod",
    "reservation_amortized_upfront_cost_for_usage": "reservation/AmortizedUpfrontCostForUsage",
    "reservation_recurring_fee_for_usage": "reservation/RecurringFeeForUsage",
    "reservation_unused_quantity": "reservation/UnusedQuantity",
    "reservation_unused_recurring_fee": "reservation/UnusedRecurringFee",
    "pricing_term": "pricing/term",
    "pricing_unit": "pricing/unit",
    "product_sku": "product/sku",
    "product_product_name": "product/ProductName",
    "product_product_family": "product/productFamily",
    "product_servicecode": "product/servicecode",
    "product_region": "product/region",
    "product_instance_type": "product/instanceType",
    "product_memory": "product/memory",
    "product_vcpu": "product/vcpu",
    "reservation_number_of_reservations": "reservation/NumberOfReservations",
    "reservation_units_per_reservation": "reservation/UnitsPerReservation",
    "reservation_start_time": "reservation/StartTime",
    "reservation_end_time": "reservation/EndTime",
}

ALL_RESOURCE_TAG_PREFIX = "resourceTags/"
RESOURCE_TAG_USER_PREFIX = "resourceTags/user:"
COST_CATEGORY_PREFIX = "costCategory/"
CSV_COLUMN_PREFIX = (
    ALL_RESOURCE_TAG_PREFIX,
    COST_CATEGORY_PREFIX,
    "bill/",
    "lineItem/",
    "pricing/",
    "discount/",
    "product/sku",
)


# pylint: disable=too-few-public-methods
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

    def __init__(self, arn):
        """
        Parse ARN string into its component pieces.

        Args:
            arn (str): Amazon Resource Name

        """
        match = False
        self.arn = arn
        if arn:
            match = self.arn_regex.match(arn)

        if not match:
            raise SyntaxError(f"Invalid ARN: {arn}")

        for key, val in match.groupdict().items():
            setattr(self, key, val)

    def __repr__(self):
        """Return the ARN itself."""
        return self.arn


def get_assume_role_session(
    arn: AwsArn, session: str = "MasuSession", region: str = "us-east-1"
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
    client = boto3.client("sts")
    response = client.assume_role(RoleArn=str(arn), RoleSessionName=session)
    return boto3.Session(
        aws_access_key_id=response["Credentials"]["AccessKeyId"],
        aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
        aws_session_token=response["Credentials"]["SessionToken"],
        region_name=region,
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


def get_cur_report_definitions(role_arn, session=None):
    """
    Get Cost Usage Reports associated with a given RoleARN.

    Args:
        role_arn     (String) RoleARN for AWS session

    """
    if not session:
        session = get_assume_role_session(role_arn)
    cur_client = session.client("cur")
    defs = cur_client.describe_report_definitions()
    report_defs = defs.get("ReportDefinitions", [])
    return report_defs


def get_cur_report_names_in_bucket(role_arn, s3_bucket, session=None):
    """
    Get Cost Usage Reports associated with a given RoleARN.

    Args:
        role_arn     (String) RoleARN for AWS session

    Returns:
        ([String]): List of Cost Usage Report Names

    """
    report_defs = get_cur_report_definitions(role_arn, session)
    report_names = []
    for report in report_defs:
        if s3_bucket == report["S3Bucket"]:
            report_names.append(report["ReportName"])
    return report_names


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


def get_provider_uuid_from_arn(role_arn):
    """Returns provider_uuid given the arn."""
    aws_creds = {"role_arn": f"{role_arn}"}
    query = Provider.objects.filter(authentication_id__credentials=aws_creds)
    if query.first():
        return query.first().uuid
    return None


def get_account_alias_from_role_arn(role_arn, session=None):
    """
    Get account ID for given RoleARN.

    Args:
        role_arn     (String) AWS IAM RoleARN

    Returns:
        (String): Account ID

    """
    provider_uuid = get_provider_uuid_from_arn(role_arn)
    context_key = "aws_list_account_aliases"
    if not session:
        session = get_assume_role_session(role_arn)
    iam_client = session.client("iam")

    account_id = role_arn.split(":")[-2]
    alias = account_id

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        context = provider_accessor.get_additional_context()
        list_aliases = context.get(context_key, True)

    if list_aliases:
        try:
            alias_response = iam_client.list_account_aliases()
            alias_list = alias_response.get("AccountAliases", [])
            # Note: Boto3 docs states that you can only have one alias per account
            # so the pop() should be ok...
            alias = alias_list.pop() if alias_list else None
        except ClientError as err:
            LOG.info("Unable to list account aliases.  Reason: %s", str(err))
            context[context_key] = False
            with ProviderDBAccessor(provider_uuid) as provider_accessor:
                provider_accessor.set_additional_context(context)

    return (account_id, alias)


def get_account_names_by_organization(role_arn, session=None):
    """
    Get account ID for given RoleARN.

    Args:
        role_arn     (String) AWS IAM RoleARN

    Returns:
        (list): Dictionaries of accounts with id, name keys

    """
    context_key = "crawl_hierarchy"
    provider_uuid = get_provider_uuid_from_arn(role_arn)
    if not session:
        session = get_assume_role_session(role_arn)
    all_accounts = []

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        context = provider_accessor.get_additional_context()
        crawlable = context.get(context_key, True)

    if crawlable:
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


def get_bills_from_provider(provider_uuid, schema, start_date=None, end_date=None):
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
        start_date = start_date.strftime("%Y-%m-%d")

    if isinstance(end_date, (datetime.datetime, datetime.date)):
        end_date = end_date.strftime("%Y-%m-%d")

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider = provider_accessor.get_provider()

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
            bills = bills.all()

    return bills


def get_s3_resource():  # pragma: no cover
    """
    Obtain the s3 session client
    """
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    aws_session = boto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET,
        region_name=settings.S3_REGION,
    )
    s3_resource = aws_session.resource("s3", endpoint_url=settings.S3_ENDPOINT, config=config)
    return s3_resource


def copy_data_to_s3_bucket(request_id, path, filename, data, manifest_id=None, context={}):
    """
    Copies data to s3 bucket file
    """
    upload = None
    upload_key = f"{path}/{filename}"
    extra_args = {}
    if manifest_id:
        extra_args = {"Metadata": {"ManifestId": str(manifest_id)}}
    try:
        s3_resource = get_s3_resource()
        s3_obj = {"bucket_name": settings.S3_BUCKET_NAME, "key": upload_key}
        upload = s3_resource.Object(**s3_obj)
        upload.upload_fileobj(data, ExtraArgs=extra_args)
    except (EndpointConnectionError, ClientError) as err:
        msg = f"Unable to copy data to {upload_key} in bucket {settings.S3_BUCKET_NAME}.  Reason: {str(err)}"
        LOG.info(log_json(request_id, msg, context))
    return upload


def copy_local_report_file_to_s3_bucket(
    request_id, s3_path, full_file_path, local_filename, manifest_id, start_date, context={}
):
    """
    Copies local report file to s3 bucket
    """
    if s3_path:
        LOG.info(f"copy_local_report_file_to_s3_bucket: {s3_path} {full_file_path}")
        with open(full_file_path, "rb") as fin:
            copy_data_to_s3_bucket(request_id, s3_path, local_filename, fin, manifest_id, context)


def copy_hcs_data_to_s3_bucket(request_id, path, filename, data, finalize=False, context={}):
    """
    Copies HCS data to s3 bucket location
    """
    upload = None
    upload_key = f"{path}/{filename}"
    extra_args = {"Metadata": {"finalized": str(finalize)}}

    try:
        s3_resource = get_s3_resource()
        s3_obj = {"bucket_name": settings.S3_BUCKET_NAME, "key": upload_key}
        upload = s3_resource.Object(**s3_obj)
        upload.upload_fileobj(data, ExtraArgs=extra_args)
    except (EndpointConnectionError, ClientError) as err:
        msg = f"Unable to copy data to {upload_key} in bucket {settings.S3_BUCKET_NAME}.  Reason: {str(err)}"
        LOG.info(log_json(request_id, msg, context))
    return upload


def copy_local_hcs_report_file_to_s3_bucket(
    request_id, s3_path, full_file_path, local_filename, finalize=False, context={}
):
    """
    Copies local report file to s3 bucket
    """
    if s3_path and settings.ENABLE_S3_ARCHIVING:
        LOG.info(f"copy_local_HCS_report_file_to_s3_bucket: {s3_path} {full_file_path}")
        with open(full_file_path, "rb") as fin:
            copy_hcs_data_to_s3_bucket(request_id, s3_path, local_filename, fin, finalize, context)


def remove_files_not_in_set_from_s3_bucket(request_id, s3_path, manifest_id, context={}):
    """
    Removes all files in a given prefix if they are not within the given set.
    """
    removed = []
    if s3_path:
        try:
            s3_resource = get_s3_resource()
            existing_objects = s3_resource.Bucket(settings.S3_BUCKET_NAME).objects.filter(Prefix=s3_path)
            for obj_summary in existing_objects:
                existing_object = obj_summary.Object()
                metadata = existing_object.metadata
                manifest = metadata.get("manifestid")
                manifest_id_str = str(manifest_id)
                key = existing_object.key
                if manifest != manifest_id_str:
                    s3_resource.Object(settings.S3_BUCKET_NAME, key).delete()
                    removed.append(key)
            if removed:
                msg = f"Removed files from s3 bucket {settings.S3_BUCKET_NAME}: {','.join(removed)}."
                LOG.info(log_json(request_id, msg, context))
        except (EndpointConnectionError, ClientError) as err:
            msg = f"Unable to remove data in bucket {settings.S3_BUCKET_NAME}.  Reason: {str(err)}"
            LOG.info(log_json(request_id, msg, context))
    return removed


def handle_user_defined_json_columns(data_frame, columns, column_prefix):
    """Given a prefix convert multiple dataframe columns into a single json column."""

    def scrub_resource_col_name(res_col_name):
        return res_col_name.replace(column_prefix, "")

    columns_of_interest = [column for column in columns if column_prefix in column]
    unique_keys = {scrub_resource_col_name(column) for column in columns_of_interest}

    df = data_frame[columns_of_interest]
    column_dict = df.apply(
        lambda row: {scrub_resource_col_name(column): value for column, value in row.items() if value}, axis=1
    )
    column_dict.where(column_dict.notna(), lambda _: [{}], inplace=True)

    return column_dict.apply(json.dumps), unique_keys


def check_aws_custom_columns(col_names):
    REQUIRED_COLS = set(utils.CSV_ALT_COLUMNS["AWS"])
    missing_cols = False
    if not set(col_names).issuperset(REQUIRED_COLS):
        missing_cols = True
    return missing_cols, REQUIRED_COLS


def aws_post_processor(data_frame):
    """
    Consume the AWS data and add a column creating a dictionary for the aws tags
    """
    org_columns = data_frame.columns.unique()
    columns = []
    for col in org_columns:
        if "/" not in col and COL_TRANSLATION.get(col):
            data_frame = data_frame.rename(columns={col: COL_TRANSLATION[col]})
            columns.append(COL_TRANSLATION[col])
    columns = set(TRINO_REQUIRED_COLUMNS).union(data_frame)
    columns = sorted(list(columns))

    tags, unique_keys = handle_user_defined_json_columns(data_frame, columns, RESOURCE_TAG_USER_PREFIX)
    data_frame["resourceTags"] = tags

    cost_categories, _ = handle_user_defined_json_columns(data_frame, columns, COST_CATEGORY_PREFIX)
    data_frame["costCategory"] = cost_categories

    # Make sure we have entries for our required columns
    data_frame = data_frame.reindex(columns=columns)

    columns = list(data_frame)
    column_name_map = {}
    drop_columns = []
    for column in columns:
        new_col_name = strip_characters_from_column_name(column)
        column_name_map[column] = new_col_name
        if ALL_RESOURCE_TAG_PREFIX in column or COST_CATEGORY_PREFIX in column:
            drop_columns.append(column)
    data_frame = data_frame.drop(columns=drop_columns)
    data_frame = data_frame.rename(columns=column_name_map)
    return (data_frame, unique_keys)


def aws_generate_daily_data(data_frame):
    """Given a dataframe, group the data to create daily data."""
    # usage_start = data_frame["lineitem_usagestartdate"]
    # usage_start_dates = usage_start.apply(lambda row: row.date())
    # data_frame["usage_start"] = usage_start_dates
    daily_data_frame = data_frame.groupby(
        [
            "lineitem_resourceid",
            pd.Grouper(key="lineitem_usagestartdate", freq="D"),
            "bill_payeraccountid",
            "lineitem_usageaccountid",
            "lineitem_legalentity",
            "lineitem_lineitemdescription",
            "bill_billingentity",
            "lineitem_productcode",
            "lineitem_availabilityzone",
            "product_productfamily",
            "product_instancetype",
            "product_region",
            "pricing_unit",
            "resourcetags",
            "costcategory",
        ],
        dropna=False,
    ).agg(
        {
            "lineitem_usageamount": ["sum"],
            "lineitem_normalizationfactor": ["max"],
            "lineitem_normalizedusageamount": ["sum"],
            "lineitem_currencycode": ["max"],
            "lineitem_unblendedrate": ["max"],
            "lineitem_unblendedcost": ["sum"],
            "lineitem_blendedrate": ["max"],
            "lineitem_blendedcost": ["sum"],
            "pricing_publicondemandcost": ["sum"],
            "pricing_publicondemandrate": ["max"],
            "savingsplan_savingsplaneffectivecost": ["sum"],
            "product_productname": ["max"],
            "bill_invoiceid": ["max"],
        }
    )
    columns = daily_data_frame.columns.droplevel(1)
    daily_data_frame.columns = columns
    daily_data_frame.reset_index(inplace=True)

    return daily_data_frame


def match_openshift_resources_and_labels(data_frame, cluster_topologies, matched_tags):
    """Filter a dataframe to the subset that matches an OpenShift source."""
    resource_ids = chain.from_iterable(
        cluster_topology.get("resource_ids", []) for cluster_topology in cluster_topologies
    )
    resource_ids = tuple(resource_ids)
    resource_id_df = data_frame["lineitem_resourceid"]

    LOG.info("Matching OpenShift on AWS by resource ID.")
    resource_id_matched = resource_id_df.str.endswith(resource_ids)
    data_frame["resource_id_matched"] = resource_id_matched

    tags = data_frame["resourcetags"]
    tags = tags.str.lower()

    special_case_tag_matched = tags.str.contains(
        "|".join(["openshift_cluster", "openshift_project", "openshift_node"])
    )
    data_frame["special_case_tag_matched"] = special_case_tag_matched

    if matched_tags:
        tag_keys = []
        tag_values = []
        for tag in matched_tags:
            tag_keys.extend(list(tag.keys()))
            tag_values.extend(list(tag.values()))

        tag_matched = tags.str.contains("|".join(tag_keys)) & tags.str.contains("|".join(tag_values))
        data_frame["tag_matched"] = tag_matched
        any_tag_matched = tag_matched.any()

        if any_tag_matched:
            tag_df = pd.concat([tags, tag_matched], axis=1)
            tag_df.columns = ("tags", "tag_matched")
            tag_subset = tag_df[tag_df.tag_matched == True].tags  # noqa: E712

            LOG.info("Matching OpenShift on AWS tags.")

            matched_tag = tag_subset.apply(match_openshift_labels, args=(matched_tags,))
            data_frame["matched_tag"] = matched_tag
            data_frame["matched_tag"].fillna(value="", inplace=True)
        else:
            data_frame["matched_tag"] = ""
    else:
        data_frame["tag_matched"] = False
        data_frame["matched_tag"] = ""
    openshift_matched_data_frame = data_frame[
        (data_frame["resource_id_matched"] == True)  # noqa: E712
        | (data_frame["special_case_tag_matched"] == True)  # noqa: E712
        | (data_frame["matched_tag"] != "")  # noqa: E712
    ]

    openshift_matched_data_frame["uuid"] = openshift_matched_data_frame.apply(lambda _: str(uuid.uuid4()), axis=1)
    openshift_matched_data_frame = openshift_matched_data_frame.drop(
        columns=["special_case_tag_matched", "tag_matched"]
    )

    return openshift_matched_data_frame


def get_column_converters():
    """Return source specific parquet column converters."""
    return {
        "bill/billingperiodstartdate": ciso8601.parse_datetime,
        "bill/billingperiodenddate": ciso8601.parse_datetime,
        "lineitem/usagestartdate": ciso8601.parse_datetime,
        "lineitem/usageenddate": ciso8601.parse_datetime,
        "lineitem/usageamount": safe_float,
        "lineitem/normalizationfactor": safe_float,
        "lineitem/normalizedusageamount": safe_float,
        "lineitem/unblendedrate": safe_float,
        "lineitem/unblendedcost": safe_float,
        "lineitem/blendedrate": safe_float,
        "lineitem/blendedcost": safe_float,
        "pricing/publicondemandcost": safe_float,
        "pricing/publicondemandrate": safe_float,
        "savingsplan/savingsplaneffectivecost": safe_float,
        "bill_billing_period_start_date": ciso8601.parse_datetime,
        "bill_billing_period_end_date": ciso8601.parse_datetime,
        "line_item_usage_start_date": ciso8601.parse_datetime,
        "line_item_usage_end_date": ciso8601.parse_datetime,
        "line_item_usage_amount": safe_float,
        "line_item_normalization_factor": safe_float,
        "line_item_normalized_usage_amount": safe_float,
        "line_item_unblended_rate": safe_float,
        "line_item_unblended_cost": safe_float,
        "line_item_blended_rate": safe_float,
        "line_item_blended_cost": safe_float,
        "pricing_public_on_demand_cost": safe_float,
        "pricing_public_on_demand_rate": safe_float,
        "savings_plan_savings_plan_effective_cost": safe_float,
    }
