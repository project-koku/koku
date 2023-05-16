#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Amazon Web services provider implementation to be used by Koku."""
import logging

import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from botocore.exceptions import ParamValidationError
from requests.exceptions import ConnectionError as BotoConnectionError
from rest_framework import serializers  # meh

from ..provider_errors import ProviderErrors
from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.models import Provider
from masu.processor import ALLOWED_COMPRESSIONS
from masu.util.aws.common import AwsArn

LOG = logging.getLogger(__name__)


def _get_sts_access(credentials):
    """Get for sts access."""
    # create an STS client
    arn = AwsArn(credentials)
    sts_client = boto3.client("sts")

    credentials = {}
    error_message = f"Unable to assume role with ARN {arn.arn}."
    try:
        # Call the assume_role method of the STSConnection object and pass the role
        # ARN and a role session name.
        if arn.external_id:
            assumed_role = sts_client.assume_role(
                RoleArn=arn.arn, RoleSessionName="AccountCreationSession", ExternalId=arn.external_id
            )
        else:
            assumed_role = sts_client.assume_role(RoleArn=arn.arn, RoleSessionName="AccountCreationSession")
        aws_credentials = assumed_role.get("Credentials")
    except ParamValidationError as param_error:
        LOG.warn(msg=error_message)
        LOG.info(param_error)
        # We can't use the exc_info here because it will print
        # a traceback that gets picked up by sentry:
        # https://github.com/project-koku/koku/issues/1483
    except (ClientError, BotoConnectionError, NoCredentialsError) as boto_error:
        LOG.warn(msg=error_message, exc_info=boto_error)

    # return a kwargs-friendly format
    return dict(
        aws_access_key_id=aws_credentials.get("AccessKeyId"),
        aws_secret_access_key=aws_credentials.get("SecretAccessKey"),
        aws_session_token=aws_credentials.get("SessionToken"),
    )


def _check_s3_access(bucket, credentials, region_name="us-east-1"):
    """Check for access to s3 bucket."""
    s3_exists = True
    s3_resource = boto3.resource("s3", region_name=region_name, **credentials)
    try:
        s3_resource.meta.client.head_bucket(Bucket=bucket)
    except (ClientError, BotoConnectionError) as boto_error:
        message = f"Unable to access bucket {bucket} with given credentials."
        LOG.warn(msg=message, exc_info=boto_error)
        s3_exists = False
    return s3_exists


def _check_cost_report_access(credential_name, credentials, region_name="us-east-1", bucket=None):
    """Check for provider cost and usage report access."""
    cur_client = boto3.client("cur", region_name=region_name, **credentials)
    reports = None

    try:
        response = cur_client.describe_report_definitions()
        reports = response.get("ReportDefinitions")
    except (ClientError, BotoConnectionError) as boto_error:
        key = ProviderErrors.AWS_NO_REPORT_FOUND
        message = f"Unable to obtain cost and usage report definition data with {credential_name}."
        LOG.warn(msg=message, exc_info=boto_error)
        raise serializers.ValidationError(error_obj(key, message))

    if reports and bucket:
        # filter report definitions to reports with a matching S3 bucket name.
        bucket_matched = list(filter(lambda rep: bucket in rep.get("S3Bucket"), reports))

        if not bucket_matched:
            key = ProviderErrors.AWS_REPORT_CONFIG
            msg = (
                f"Cost management requires that an AWS Cost and Usage Report is configured for bucket: {str(bucket)}."
            )
            raise serializers.ValidationError(error_obj(key, msg))

        for report in bucket_matched:
            if report.get("Compression") not in ALLOWED_COMPRESSIONS:
                key = ProviderErrors.AWS_COMPRESSION_REPORT_CONFIG
                internal_msg = (
                    f"{report.get('Compression')} compression is not supported. "
                    f"Reports must use GZIP compression format."
                )
                raise serializers.ValidationError(error_obj(key, internal_msg))
            if "RESOURCES" not in report.get("AdditionalSchemaElements"):
                key = ProviderErrors.AWS_REPORT_CONFIG
                msg = f"Required Resource IDs are not included in report {report.get('ReportName')}"
                raise serializers.ValidationError(error_obj(key, msg))


class AWSProvider(ProviderInterface):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_AWS

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that the S3 bucket exists and is reachable."""

        role_arn = credentials.get("role_arn")
        if not role_arn or role_arn.isspace():
            key = ProviderErrors.AWS_MISSING_ROLE_ARN
            message = ProviderErrors.AWS_MISSING_ROLE_ARN_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        storage_resource_name = data_source.get("bucket")
        if not storage_resource_name or storage_resource_name.isspace():
            key = ProviderErrors.AWS_BUCKET_MISSING
            message = ProviderErrors.AWS_BUCKET_MISSING_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        storage_only = data_source.get("storage_only")
        if storage_only:
            # Limited bucket access without CUR
            return True

        creds = _get_sts_access(credentials)
        # if any values in creds are None, the dict won't be empty
        if bool({k: v for k, v in creds.items() if not v}):
            key = ProviderErrors.AWS_ROLE_ARN_UNREACHABLE
            internal_message = f"Unable to access account resources with ARN {role_arn}."
            raise serializers.ValidationError(error_obj(key, internal_message))

        region_kwargs = {}
        if region_name := data_source.get("bucket_region"):
            region_kwargs["region_name"] = region_name

        s3_exists = _check_s3_access(storage_resource_name, creds, **region_kwargs)
        if not s3_exists:
            key = ProviderErrors.AWS_BILLING_SOURCE_NOT_FOUND
            internal_message = f"Bucket {storage_resource_name} could not be found with {role_arn}."
            raise serializers.ValidationError(error_obj(key, internal_message))

        _check_cost_report_access(role_arn, creds, bucket=storage_resource_name, **region_kwargs)

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []

    def is_file_reachable(self, source, reports_list):
        """Verify that report files are accessible in S3."""
        credentials = source.authentication.credentials
        bucket = source.billing_source.data_source.get("bucket")
        creds = _get_sts_access(credentials)
        s3_client = boto3.client("s3", **creds)
        for report in reports_list:
            try:
                s3_client.get_object(Bucket=bucket, Key=report)
            except ClientError as ex:
                if ex.response["Error"]["Code"] == "NoSuchKey":
                    key = ProviderErrors.AWS_REPORT_NOT_FOUND
                    internal_message = f"File {report} could not be found within bucket {bucket}."
                    raise serializers.ValidationError(error_obj(key, internal_message))
