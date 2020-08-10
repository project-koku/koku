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

LOG = logging.getLogger(__name__)


def _get_sts_access(provider_resource_name):
    """Get for sts access."""
    # create an STS client
    sts_client = boto3.client("sts")

    credentials = dict()
    error_message = f"Unable to assume role with ARN {provider_resource_name}."
    try:
        # Call the assume_role method of the STSConnection object and pass the role
        # ARN and a role session name.
        assumed_role = sts_client.assume_role(RoleArn=provider_resource_name, RoleSessionName="AccountCreationSession")
        credentials = assumed_role.get("Credentials")
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
        aws_access_key_id=credentials.get("AccessKeyId"),
        aws_secret_access_key=credentials.get("SecretAccessKey"),
        aws_session_token=credentials.get("SessionToken"),
    )


def _check_s3_access(bucket, credentials):
    """Check for access to s3 bucket."""
    s3_exists = True
    s3_resource = boto3.resource("s3", **credentials)
    try:
        s3_resource.meta.client.head_bucket(Bucket=bucket)
    except (ClientError, BotoConnectionError) as boto_error:
        message = f"Unable to access bucket {bucket} with given credentials."
        LOG.warn(msg=message, exc_info=boto_error)
        s3_exists = False
    return s3_exists


def _check_org_access(credentials):
    """Check for provider organization access."""
    access_ok = True
    org_client = boto3.client("organizations", **credentials)
    try:
        org_client.describe_organization()
    except (ClientError, BotoConnectionError) as boto_error:
        message = "Unable to describe organizationwith given credentials."
        LOG.warn(msg=message, exc_info=boto_error)
        access_ok = False
    return access_ok


def _check_cost_report_access(credential_name, credentials, region="us-east-1", bucket=None):
    """Check for provider cost and usage report access."""
    cur_client = boto3.client("cur", region_name=region, **credentials)
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

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that the S3 bucket exists and is reachable."""
        if not credential_name or credential_name.isspace():
            key = ProviderErrors.AWS_MISSING_RESOURCE_NAME
            message = ProviderErrors.AWS_MISSING_RESOURCE_NAME_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        creds = _get_sts_access(credential_name)
        # if any values in creds are None, the dict won't be empty
        if bool({k: v for k, v in creds.items() if not v}):
            key = ProviderErrors.AWS_RESOURCE_NAME_UNREACHABLE
            internal_message = f"Unable to access account resources with ARN {credential_name}."
            raise serializers.ValidationError(error_obj(key, internal_message))

        if not storage_resource_name or storage_resource_name.isspace():
            key = ProviderErrors.AWS_BUCKET_MISSING
            message = ProviderErrors.AWS_BUCKET_MISSING_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        s3_exists = _check_s3_access(storage_resource_name, creds)
        if not s3_exists:
            key = ProviderErrors.AWS_BILLING_SOURCE_NOT_FOUND
            internal_message = f"Bucket {storage_resource_name} could not be found with {credential_name}."
            raise serializers.ValidationError(error_obj(key, internal_message))

        _check_cost_report_access(credential_name, creds, bucket=storage_resource_name)

        org_access = _check_org_access(creds)
        if not org_access:
            message = f"Unable to obtain organization data with {credential_name}."
            LOG.info(message)
        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
