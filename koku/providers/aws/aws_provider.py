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
    access_key_id = None
    secret_access_key = None
    session_token = None
    # create an STS client
    sts_client = boto3.client('sts')

    try:
        # Call the assume_role method of the STSConnection object and pass the role
        # ARN and a role session name.
        assumed_role = sts_client.assume_role(
            RoleArn=provider_resource_name,
            RoleSessionName='AccountCreationSession'
        )
        credentials = assumed_role.get('Credentials')
        if credentials:
            access_key_id = credentials.get('AccessKeyId')
            secret_access_key = credentials.get('SecretAccessKey')
            session_token = credentials.get('SessionToken')
    except (ClientError, BotoConnectionError, NoCredentialsError, ParamValidationError) as boto_error:
        LOG.exception(boto_error)

    return (access_key_id, secret_access_key, session_token)


def _check_s3_access(access_key_id, secret_access_key,
                     session_token, bucket):
    """Check for access to s3 bucket."""
    s3_exists = True
    s3_resource = boto3.resource(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
    )
    try:
        s3_resource.meta.client.head_bucket(Bucket=bucket)
    except (ClientError, BotoConnectionError) as boto_error:
        LOG.exception(boto_error)
        s3_exists = False
    return s3_exists


def _get_configured_sns_topics(access_key_id, secret_access_key, session_token, bucket):
    """Get a list of configured SNS topics."""
    # create an SNS client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
    )
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
    except (ClientError, BotoConnectionError, NoCredentialsError, ParamValidationError) as boto_error:
        LOG.exception(boto_error)

    return topics


def _check_cost_report_access(access_key_id, secret_access_key, session_token,
                              region='us-east-1'):
    """Check for provider cost and usage report access."""
    access_ok = True
    cur_client = boto3.client(
        'cur',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
        region_name=region
    )
    try:
        cur_client.describe_report_definitions()
    except (ClientError, BotoConnectionError) as boto_error:
        LOG.exception(boto_error)
        access_ok = False
    return access_ok


class AWSProvider(ProviderInterface):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return 'AWS'

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that the S3 bucket exists and is reachable."""
        access_key_id, secret_access_key, session_token = _get_sts_access(
            credential_name)
        if (access_key_id is None or access_key_id is None or session_token is None):
            key = 'provider_resource_name'
            message = 'Unable to obtain credentials with using {}.'.format(
                credential_name)
            raise serializers.ValidationError(error_obj(key, message))

        if not storage_resource_name:
            key = 'bucket'
            message = 'Bucket is a required parameter for AWS.'
            raise serializers.ValidationError(error_obj(key, message))

        s3_exists = _check_s3_access(access_key_id, secret_access_key,
                                     session_token, storage_resource_name)
        if not s3_exists:
            key = 'bucket'
            message = 'Bucket {} could not be found with {}.'.format(
                storage_resource_name, credential_name)
            raise serializers.ValidationError(error_obj(key, message))

        cur_access = _check_cost_report_access(access_key_id, secret_access_key,
                                               session_token)
        if not cur_access:
            key = 'provider_resource_name'
            message = 'Unable to obtain cost and usage report ' \
                'definition data with {}.'.format(
                    credential_name)
            raise serializers.ValidationError(error_obj(key, message))

        sns_topics = _get_configured_sns_topics(access_key_id, secret_access_key,
                                                session_token, storage_resource_name)
        topics_string = ', '.join(sns_topics)
        if sns_topics:
            LOG.info('S3 Notification Topics: %s for S3 bucket: %s',
                     topics_string, storage_resource_name)
        else:
            LOG.info('SNS is not configured for S3 bucket %s', storage_resource_name)
