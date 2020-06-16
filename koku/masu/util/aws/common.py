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
"""AWS utility functions."""
import datetime
import logging
import re
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta
from django.conf import settings
from tenant_schemas.utils import schema_context

from api.common import log_json
from api.models import Provider
from masu.config import Config
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util import common as utils

LOG = logging.getLogger(__name__)


def get_assume_role_session(arn, session="MasuSession"):
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
        region_name="us-east-1",
    )


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
    return "{}-{}".format(start_month.strftime(timeformat), end_month.strftime(timeformat))


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


def get_account_alias_from_role_arn(role_arn, session=None):
    """
    Get account ID for given RoleARN.

    Args:
        role_arn     (String) AWS IAM RoleARN

    Returns:
        (String): Account ID

    """
    if not session:
        session = get_assume_role_session(role_arn)
    iam_client = session.client("iam")

    account_id = role_arn.split(":")[-2]
    alias = account_id
    try:
        alias_response = iam_client.list_account_aliases()
        alias_list = alias_response.get("AccountAliases", [])
        # Note: Boto3 docs states that you can only have one alias per account
        # so the pop() should be ok...
        alias = alias_list.pop() if alias_list else None
    except ClientError as err:
        LOG.info("Unable to list account aliases.  Reason: %s", str(err))

    return (account_id, alias)


def get_account_names_by_organization(role_arn, session=None):
    """
    Get account ID for given RoleARN.

    Args:
        role_arn     (String) AWS IAM RoleARN

    Returns:
        (list): Dictionaries of accounts with id, name keys

    """
    if not session:
        session = get_assume_role_session(role_arn)
    org_client = session.client("organizations")
    all_accounts = []
    try:
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


def get_s3_resource():
    """
    Obtain the s3 session client
    """
    aws_session = boto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET,
        region_name=settings.S3_REGION,
    )
    s3_resource = aws_session.resource("s3")
    return s3_resource


def copy_data_to_s3_bucket(request_id, path, filename, data, manifest_id=None, context={}):
    """
    Copies data to s3 bucket file
    """
    if not settings.ENABLE_S3_ARCHIVING:
        return None

    upload = None
    upload_key = f"{path}/{filename}"
    try:
        s3_resource = get_s3_resource()
        s3_obj = {"bucket_name": settings.S3_BUCKET_NAME, "key": upload_key}
        upload = s3_resource.Object(**s3_obj)
        put_value = {"Body": data}
        if manifest_id:
            put_value["Metadata"] = {"ManifestId": str(manifest_id)}
        upload.put(**put_value)
    except ClientError as err:
        msg = f"Unable to copy data to {upload_key} in bucket {settings.S3_BUCKET_NAME}.  Reason: {str(err)}"
        LOG.info(log_json(request_id, msg, context))
    return upload


def _get_path_prefix(account, provider_uuid, start_date):
    """
    Get the S3 bucket prefix
    """
    year = start_date.strftime("%Y")
    month = start_date.strftime("%m")
    path_prefix = f"{Config.WAREHOUSE_PATH}/{Config.CSV_DATA_TYPE}"
    path = f"{path_prefix}/{account}/{provider_uuid}/{year}/{month}"
    return path


def copy_local_report_file_to_s3_bucket(
    request_id, account, provider_uuid, full_file_path, local_filename, manifest_id, start_date, context={}
):
    """
    Copies local report file to s3 bucket
    """
    if start_date:
        path = _get_path_prefix(account, provider_uuid, start_date)
        with open(full_file_path, "rb") as fin:
            data = BytesIO(fin.read())
            copy_data_to_s3_bucket(request_id, path, local_filename, data, manifest_id, context)


def remove_files_not_in_set_from_s3_bucket(request_id, account, provider_uuid, start_date, manifest_id, context={}):
    """
    Removes all files in a given prefix if they are not within the given set.
    """
    if not settings.ENABLE_S3_ARCHIVING:
        return None

    removed = []
    if start_date:
        try:
            path = _get_path_prefix(account, provider_uuid, start_date)
            s3_resource = get_s3_resource()
            existing_objects = s3_resource.Bucket(settings.S3_BUCKET_NAME).objects.filter(Prefix=path)
            for obj_summary in existing_objects:
                existing_object = obj_summary.Object()
                metadata = existing_object.metadata
                manifest = metadata.get("ManifestId")
                key = existing_object.key
                if manifest is not manifest_id:
                    s3_resource.Object(settings.S3_BUCKET_NAME, key).delete()
                    removed.append(key)
            if removed:
                msg = f"Removed files from s3 bucket {settings.S3_BUCKET_NAME}: {','.join(removed)}."
                LOG.info(log_json(request_id, msg, context))
        except ClientError as err:
            msg = f"Unable to remove data in bucket {settings.S3_BUCKET_NAME}.  Reason: {str(err)}"
            LOG.info(log_json(request_id, msg, context))
    return removed


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
        self.arn = arn
        match = self.arn_regex.match(arn)

        if not match:
            raise SyntaxError(f"Invalid ARN: {arn}")

        for key, val in match.groupdict().items():
            setattr(self, key, val)

    def __repr__(self):
        """Return the ARN itself."""
        return self.arn
