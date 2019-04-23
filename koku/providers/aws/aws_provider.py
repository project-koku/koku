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
from botocore.exceptions import ClientError, NoCredentialsError, ParamValidationError
from django.utils.translation import ugettext as _
from requests.exceptions import ConnectionError as BotoConnectionError
from rest_framework import serializers   # meh

from ..provider_interface import ProviderInterface

LOG = logging.getLogger(__name__)


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


def _get_sts_access(provider_resource_name):
    """Get for sts access."""
    # create an STS client
    sts_client = boto3.client('sts')

    credentials = dict()
    try:
        # Call the assume_role method of the STSConnection object and pass the role
        # ARN and a role session name.
        assumed_role = sts_client.assume_role(
            RoleArn=provider_resource_name,
            RoleSessionName='AccountCreationSession'
        )
        credentials = assumed_role.get('Credentials')
    except (ClientError, BotoConnectionError, NoCredentialsError, ParamValidationError) as boto_error:
        LOG.exception(boto_error)

    # return a kwargs-friendly format
    return dict(aws_access_key_id=credentials.get('AccessKeyId'),
                aws_secret_access_key=credentials.get('SecretAccessKey'),
                aws_session_token=credentials.get('SessionToken'))


def _check_s3_access(bucket, credentials):
    """Check for access to s3 bucket."""
    s3_exists = True
    s3_resource = boto3.resource('s3', **credentials)
    try:
        s3_resource.meta.client.head_bucket(Bucket=bucket)
    except (ClientError, BotoConnectionError) as boto_error:
        LOG.exception(boto_error)
        s3_exists = False
    return s3_exists


def _get_configured_sns_topics(bucket, credentials):
    """Get a list of configured SNS topics."""
    # create an SNS client
    s3_client = boto3.client('s3', **credentials)
    topics = []
    try:
        notification_configuration = s3_client.get_bucket_notification_configuration(Bucket=bucket)
        configuration = notification_configuration.get('TopicConfigurations', None)
        if configuration:
            for event in configuration:
                # FIXME: Once we complete the Masu #75 userstory we should verify that
                # the correct TopicArn is configured as well as the correct
                # events (i.e. 's3:ObjectCreated:*'). For now lets just keep a list of all
                # topics subscribed to and log it.
                topic_arn = event.get('TopicArn')
                topics.append(topic_arn) if topic_arn else None
    except (ClientError, BotoConnectionError,
            NoCredentialsError, ParamValidationError) as boto_error:
        LOG.exception(boto_error)

    return topics


def _check_cost_report_access(credential_name, credentials,
                              region='us-east-1', bucket=None):
    """Check for provider cost and usage report access."""
    cur_client = boto3.client('cur', region_name=region, **credentials)
    reports = None

    try:
        response = cur_client.describe_report_definitions()
        reports = response.get('ReportDefinitions')
    except (ClientError, BotoConnectionError) as boto_error:
        LOG.exception(boto_error)
        key = 'authentication.provider_resource_name'
        message = 'Unable to obtain cost and usage report ' \
                  'definition data with {}.'.format(credential_name)
        raise serializers.ValidationError(error_obj(key, message))

    if reports and bucket:
        # filter report definitions to reports with a matching S3 bucket name.
        bucket_matched = list(
            filter(lambda rep: bucket in rep.get('S3Bucket'),
                   reports))

        for report in bucket_matched:
            if 'RESOURCES' not in report.get('AdditionalSchemaElements'):
                key = 'report_configuration'
                msg = 'Required Resource IDs are not included ' \
                      'in report "{}".'.format(report.get('ReportName'))
                raise serializers.ValidationError(error_obj(key, msg))


class AWSProvider(ProviderInterface):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return 'AWS'

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that the S3 bucket exists and is reachable."""
        if not credential_name or credential_name.isspace():
            key = 'authentication.provider_resource_name'
            message = 'Provider resource name is a required parameter for AWS' \
                ' and must not be blank.'
            raise serializers.ValidationError(error_obj(key, message))

        creds = _get_sts_access(credential_name)
        # if any values in creds are None, the dict won't be empty
        if bool({k: v for k, v in creds.items() if not v}):
            key = 'provider_resource_name'
            message = 'Unable to access account resources with ARN {}.'.format(
                credential_name)
            raise serializers.ValidationError(error_obj(key, message))

        if not storage_resource_name or storage_resource_name.isspace():
            key = 'billing_source.bucket'
            message = 'Bucket is a required parameter for AWS and must not be blank.'
            raise serializers.ValidationError(error_obj(key, message))

        s3_exists = _check_s3_access(storage_resource_name, creds)
        if not s3_exists:
            key = 'billing_source.bucket'
            message = 'Bucket {} could not be found with {}.'.format(
                storage_resource_name, credential_name)
            raise serializers.ValidationError(error_obj(key, message))

        _check_cost_report_access(credential_name, creds, bucket=storage_resource_name)

        sns_topics = _get_configured_sns_topics(storage_resource_name, creds)
        topics_string = ', '.join(sns_topics)
        if sns_topics:
            LOG.info('S3 Notification Topics: %s for S3 bucket: %s',
                     topics_string, storage_resource_name)
        else:
            LOG.info('SNS is not configured for S3 bucket %s', storage_resource_name)

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
