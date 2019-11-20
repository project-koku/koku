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
"""Sources Model Serializers."""

from django.db import IntegrityError, transaction
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.fields import empty

from api.iam.serializers import (AdminCustomerSerializer,
                                 CustomerSerializer,
                                 UserSerializer)
from api.provider.models import (Provider,
                                 ProviderAuthentication,
                                 ProviderBillingSource,
                                 Sources)
from providers.provider_access import ProviderAccessor

from sources.storage import SourcesStorageError, add_provider_billing_source

PROVIDER_CHOICE_LIST = [provider[0].lower() for provider in Provider.PROVIDER_CHOICES]

REPORT_PREFIX_MAX_LENGTH = 64


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


def validate_field(data, valid_fields, key):
    """Validate a field."""
    message = 'One or more required fields is invalid/missing. ' + \
              f'Required fields are {valid_fields}'
    diff = set(valid_fields) - set(data)
    if not diff:
        return data
    raise serializers.ValidationError(error_obj(key, message))


class ProviderAuthenticationSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Authentication model."""

    uuid = serializers.UUIDField(read_only=True)

    # XXX: This field is DEPRECATED;
    # XXX: the credentials field should be used instead.
    provider_resource_name = serializers.CharField(
        required=False, allow_null=True, allow_blank=True)

    credentials = serializers.JSONField(allow_null=True, required=False)

    def validate(self, data):
        """Validate authentication parameters."""
        if not data.get('credentials'):
            data['credentials'] = data.get('credentials', {})
        if data.get('provider_resource_name') and not data.get('credentials'):
            data['credentials'] = {'provider_resource_name': data.get('provider_resource_name')}
        if data.get('credentials').get('provider_resource_name'):
            data['provider_resource_name'] = data.get('credentials').get('provider_resource_name')
        return data

    # pylint: disable=too-few-public-methods
    class Meta:
        """Metadata for the serializer."""

        model = ProviderAuthentication
        fields = ('uuid', 'provider_resource_name', 'credentials')


class AWSAuthenticationSerializer(ProviderAuthenticationSerializer):
    """AWS auth serializer."""


class AzureAuthenticationSerializer(ProviderAuthenticationSerializer):
    """Azure auth serializer."""

    credentials = serializers.JSONField(allow_null=True, required=True)

    def validate_credentials(self, creds):
        """Validate credentials field."""
        key = 'provider.credentials'
        fields = ['subscription_id', 'tenant_id', 'client_id', 'client_secret']
        return validate_field(creds, fields, key)


class GCPAuthenticationSerializer(ProviderAuthenticationSerializer):
    """GCP auth serializer."""


class OCPAuthenticationSerializer(ProviderAuthenticationSerializer):
    """OCP auth serializer."""


class ProviderBillingSourceSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Billing Source model."""

    uuid = serializers.UUIDField(read_only=True)

    # XXX: This field is DEPRECATED
    # XXX: the data_source field should be used instead.
    bucket = serializers.CharField(max_length=63, required=False,
                                   allow_null=True, allow_blank=True)

    data_source = serializers.JSONField(allow_null=True, required=False)

    # pylint: disable=too-few-public-methods
    class Meta:
        """Metadata for the serializer."""

        model = ProviderBillingSource
        fields = ('uuid', 'bucket', 'data_source')

    def validate(self, data):
        """Validate billing source."""
        if not data.get('data_source'):
            data['data_source'] = data.get('data_source', {})
        if (data.get('bucket') or data.get('bucket') == '') and not data.get('data_source'):
            data['data_source'] = {'bucket': data.get('bucket')}
        if data.get('data_source').get('bucket'):
            data['bucket'] = data.get('data_source').get('bucket')
        return data


class AWSBillingSourceSerializer(ProviderBillingSourceSerializer):
    """AWS billing source serializer."""


class AzureBillingSourceSerializer(ProviderBillingSourceSerializer):
    """Azure billing source serializer."""

    data_source = serializers.JSONField(allow_null=True, required=True)

    def validate_data_source(self, data_source):
        """Validate data_source field."""
        key = 'provider.data_source'
        fields = ['resource_group', 'storage_account']
        return validate_field(data_source, fields, key)


class GCPBillingSourceSerializer(ProviderBillingSourceSerializer):
    """GCP billing source serializer."""

    data_source = serializers.JSONField(allow_null=True, required=True)

    def validate(self, data):
        """Validate data_source field."""
        data_source = data.get('data_source')
        bucket = data_source.get('bucket', '')
        if not bucket:
            key = 'data_source.bucket'
            message = 'This field is required.'
            raise serializers.ValidationError(error_obj(key, message))

        report_prefix = data_source.get('report_prefix', '')
        if report_prefix:
            if len(report_prefix) > REPORT_PREFIX_MAX_LENGTH:
                key = 'data_source.report_prefix'
                message = f'Ensure this field has no more than {REPORT_PREFIX_MAX_LENGTH} characters.'
                raise serializers.ValidationError(error_obj(key, message))

        return data


class OCPBillingSourceSerializer(ProviderBillingSourceSerializer):
    """OCP billing source serializer."""


# Registry of authentication serializers.
AUTHENTICATION_SERIALIZERS = {'AWS': AWSAuthenticationSerializer,
                              'AWS-local': AWSAuthenticationSerializer,
                              'AZURE': AzureAuthenticationSerializer,
                              'AZURE-local': AzureAuthenticationSerializer,
                              'GCP': GCPAuthenticationSerializer,
                              'GCP-local': GCPAuthenticationSerializer,
                              'OCP': OCPAuthenticationSerializer,
                              'OCP_AWS': AWSAuthenticationSerializer,
                              'OCP_AZURE': AzureAuthenticationSerializer,
                              }


# Registry of billing_source serializers.
BILLING_SOURCE_SERIALIZERS = {'AWS': AWSBillingSourceSerializer,
                              'AWS-local': AWSBillingSourceSerializer,
                              'AZURE': AzureBillingSourceSerializer,
                              'AZURE-local': AzureBillingSourceSerializer,
                              'GCP': GCPBillingSourceSerializer,
                              'GCP-local': GCPBillingSourceSerializer,
                              'OCP': OCPBillingSourceSerializer,
                              'OCP_AWS': AWSBillingSourceSerializer,
                              'OCP_AZURE': AzureBillingSourceSerializer,
                              }


class SourcesSerializer(serializers.ModelSerializer):
    """Serializer for the Sources model."""

    source_id = serializers.IntegerField(required=False, read_only=True)
    name = serializers.CharField(max_length=256, required=False,
                                 allow_null=False, allow_blank=False,
                                 read_only=True)
    authentication = serializers.JSONField(required=False)
    billing_source = serializers.JSONField(required=False)
    source_type = serializers.CharField(max_length=50, required=False,
                                        allow_null=False, allow_blank=False,
                                        read_only=True)
    koku_uuid = serializers.CharField(max_length=512, required=False,
                                      allow_null=False, allow_blank=False,
                                      read_only=True)

    # pylint: disable=too-few-public-methods
    class Meta:
        """Metadata for the serializer."""

        model = Sources
        fields = ('source_id', 'name', 'source_type', 'authentication', 'billing_source',
                  'koku_uuid')

    @transaction.atomic
    def create(self, validated_data):
        """Create a provider from validated data."""
        user = None
        customer = None
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            if user.customer:
                customer = user.customer
            else:
                key = 'customer'
                message = 'Customer for requesting user could not be found.'
                raise serializers.ValidationError(error_obj(key, message))
        else:
            key = 'created_by'
            message = 'Requesting user could not be found.'
            raise serializers.ValidationError(error_obj(key, message))

        if 'billing_source' in validated_data:
            billing_source = validated_data.pop('billing_source')
            data_source = billing_source.get('data_source', {})
            bucket = data_source.get('bucket')
        else:
            # Because of a unique together constraint, this is done
            # to allow for this field to be non-required for OCP
            # but will still have a blank no-op entry in the DB
            billing_source = {'bucket': '', 'data_source': {}}
            data_source = None

        authentication = validated_data.pop('authentication')
        credentials = authentication.get('credentials')
        provider_resource_name = credentials.get('provider_resource_name')
        provider_type = validated_data['type']
        interface = ProviderAccessor(provider_type)

        if credentials and data_source and provider_type not in ['AWS', 'OCP']:
            interface.cost_usage_source_ready(credentials, data_source)
        else:
            interface.cost_usage_source_ready(provider_resource_name, bucket)

        bill, __ = ProviderBillingSource.objects.get_or_create(**billing_source)
        auth, __ = ProviderAuthentication.objects.get_or_create(**authentication)

        # We can re-use a billing source or a auth, but not the same combination.
        unique_count = Provider.objects.filter(authentication=auth)\
            .filter(billing_source=bill).count()
        if unique_count != 0:
            existing_provider = Provider.objects.filter(authentication=auth)\
                .filter(billing_source=bill).first()
            if existing_provider.type in ('AWS', 'OCP'):
                sources_auth = {'resource_name': provider_resource_name}
            elif existing_provider.type in ('AZURE', ):
                sources_auth = {'credentials': auth.credentials}
            else:
                sources_auth = {}
            source_query = Sources.objects.filter(authentication=sources_auth)
            if source_query.exists():
                source_obj = source_query.first()
                if not source_obj.koku_uuid:
                    source_obj.koku_uuid = existing_provider.uuid
                    source_obj.save()
                    return existing_provider
            error = {'Error': 'A Provider already exists with that Authentication and Billing Source'}
            raise serializers.ValidationError(error)

        provider = Provider.objects.create(**validated_data)
        provider.customer = customer
        provider.created_by = user
        provider.authentication = auth
        provider.billing_source = bill
        provider.active = True

        provider.save()
        return provider

    def _validate_billing_source(self, provider_type, billing_source):
        """Validate billing source parameters."""
        if provider_type == 'AWS':
            if not billing_source.get('bucket'):
                raise SourcesStorageError('Missing AWS bucket.')
        elif provider_type == 'AZURE':
            data_source = billing_source.get('data_source')
            if not data_source:
                raise SourcesStorageError('Missing AZURE data_source.')
            if not data_source.get('resource_group'):
                raise SourcesStorageError('Missing AZURE resource_group')
            if not data_source.get('storage_account'):
                raise SourcesStorageError('Missing AZURE storage_account')

    def update(self, instance, validated_data):
        """Update a Provider instance from validated data."""

        billing_source = validated_data.get('billing_source')
        authentication = validated_data.get('authentication')

        if billing_source:
            try:
                if instance.source_type not in ('AWS', 'AZURE'):
                    raise SourcesStorageError('Source is not AWS nor AZURE.')
                self._validate_billing_source(instance.source_type, billing_source)
                instance.billing_source = billing_source
                if instance.koku_uuid:
                    instance.pending_update = True
                    instance.save(update_fields=['billing_source', 'pending_update'])
                else:
                    instance.save()
            except Sources.DoesNotExist:
                raise SourcesStorageError('Source does not exist')

        if authentication:
            try:
                if instance.source_type not in ('AZURE',):
                    raise SourcesStorageError('Source is not AZURE.')
                auth_dict = instance.authentication
                if not auth_dict.get('credentials'):
                    raise SourcesStorageError('Missing credentials key')
                subscription_id = authentication.get('credentials', {}).get('subscription_id')
                auth_dict['credentials']['subscription_id'] = subscription_id
                instance.authentication = auth_dict
                if instance.koku_uuid:
                    instance.pending_update = True
                    instance.save(update_fields=['authentication', 'pending_update'])
                else:
                    instance.save()
            except Sources.DoesNotExist:
                raise SourcesStorageError('Source does not exist')
        return instance

