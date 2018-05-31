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
"""Provider Model Serializers."""
import logging

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, ParamValidationError
from django.db import transaction
from django.utils.translation import ugettext as _
from requests.exceptions import ConnectionError as BotoConnectionError
from rest_framework import serializers

from api.iam.models import Customer, User
from api.iam.serializers import (CustomerSerializer, UserSerializer)
from api.provider.models import (Provider,
                                 ProviderAuthentication,
                                 ProviderBillingSource)


LOG = logging.getLogger(__name__)


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class ProviderAuthenticationSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Authentication model."""

    uuid = serializers.UUIDField(read_only=True)
    provider_resource_name = serializers.CharField(required=True,
                                                   allow_null=True,
                                                   allow_blank=True)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderAuthentication
        fields = ('uuid', 'provider_resource_name')


class ProviderBillingSourceSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Billing Source model."""

    uuid = serializers.UUIDField(read_only=True)
    bucket = serializers.CharField(max_length=63, required=True,
                                   allow_null=False, allow_blank=False)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderBillingSource
        fields = ('uuid', 'bucket')


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


def _check_org_access(access_key_id, secret_access_key, session_token):
    """Check for provider organization access."""
    access_ok = True
    org_client = boto3.client(
        'organizations',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
    )
    try:
        org_client.describe_organization()
    except (ClientError, BotoConnectionError) as boto_error:
        LOG.exception(boto_error)
        access_ok = False
    return access_ok


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for the Provider  model."""

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=256, required=True,
                                 allow_null=False, allow_blank=False)
    type = serializers.ChoiceField(choices=Provider.PROVIDER_CHOICES)
    authentication = ProviderAuthenticationSerializer()
    billing_source = ProviderBillingSourceSerializer()
    customer = CustomerSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        """Metadata for the serializer."""

        model = Provider
        fields = ('uuid', 'name', 'type', 'authentication', 'billing_source',
                  'customer', 'created_by')

    @transaction.atomic
    def create(self, validated_data):
        """Create a user from validated data."""
        authentication = validated_data.pop('authentication')
        billing_source = validated_data.pop('billing_source')

        user = None
        customer = None
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = User.objects.get(pk=request.user.id)
            if user.groups.count() == 1:
                group = user.groups.first()
                customer = Customer.objects.get(pk=group.id)
            else:
                key = 'customer'
                message = 'Group for requesting user could not be found.'
                raise serializers.ValidationError(error_obj(key, message))
        else:
            key = 'created_by'
            message = 'Requesting user could not be found.'
            raise serializers.ValidationError(error_obj(key, message))

        provider_resource_name = authentication.get('provider_resource_name')
        bucket = billing_source.get('bucket')
        access_key_id, secret_access_key, session_token = _get_sts_access(
            provider_resource_name)
        if (access_key_id is None or access_key_id is None or
                session_token is None):
            key = 'provider_resource_name'
            message = 'Unable to obtain credentials with using {}.'.format(
                provider_resource_name)
            raise serializers.ValidationError(error_obj(key, message))

        s3_exists = _check_s3_access(access_key_id, secret_access_key,
                                     session_token, bucket)
        if not s3_exists:
            key = 'bucket'
            message = 'Bucket {} could not be found with {}.'.format(
                bucket, provider_resource_name)
            raise serializers.ValidationError(error_obj(key, message))

        org_access = _check_org_access(access_key_id, secret_access_key,
                                       session_token)
        if not org_access:
            key = 'provider_resource_name'
            message = 'Unable to obtain organization data with {}.'.format(
                provider_resource_name)
            raise serializers.ValidationError(error_obj(key, message))

        auth = ProviderAuthentication.objects.create(**authentication)
        bill = ProviderBillingSource.objects.create(**billing_source)
        auth.save()
        bill.save()
        provider = Provider.objects.create(**validated_data)
        provider.customer = customer
        provider.created_by = user
        provider.authentication = auth
        provider.billing_source = bill
        provider.save()
        return provider
