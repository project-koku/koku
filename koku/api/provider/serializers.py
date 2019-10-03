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

from django.db import transaction
from django.utils.translation import ugettext as _
from providers.provider_access import ProviderAccessor
from rest_framework import serializers
from rest_framework.fields import empty

from api.iam.serializers import (AdminCustomerSerializer,
                                 CustomerSerializer,
                                 UserSerializer)
from api.provider.models import (Provider,
                                 ProviderAuthentication,
                                 ProviderBillingSource,
                                 Sources)


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
        if data.get('provider_resource_name') and not data.get('credentials'):
            data['credentials'] = {'provider_resource_name': data.get('provider_resource_name')}
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
        if data.get('bucket') and not data.get('data_source'):
            data['data_source'] = {'bucket': data.get('bucket')}
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

    def validate_data_source(self, data_source):
        """Validate data_source field."""
        key = 'provider.data_source'
        fields = ['bucket']
        return validate_field(data_source, fields, key)


class OCPBillingSourceSerializer(ProviderBillingSourceSerializer):
    """OCP billing source serializer."""


# Registry of authentication serializers.
AUTHENTICATION_SERIALIZERS = {'AWS': AWSAuthenticationSerializer,
                              'AWS-local': AWSAuthenticationSerializer,
                              'AZURE': AzureAuthenticationSerializer,
                              'AZURE-local': AzureAuthenticationSerializer,
                              'GCP': GCPAuthenticationSerializer,
                              'OCP': OCPAuthenticationSerializer,
                              'OCP_AWS': AWSAuthenticationSerializer}


# Registry of billing_source serializers.
BILLING_SOURCE_SERIALIZERS = {'AWS': AWSBillingSourceSerializer,
                              'AWS-local': AWSBillingSourceSerializer,
                              'AZURE': AzureBillingSourceSerializer,
                              'AZURE-local': AzureBillingSourceSerializer,
                              'GCP': GCPBillingSourceSerializer,
                              'OCP': OCPBillingSourceSerializer,
                              'OCP_AWS': AWSBillingSourceSerializer}


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for the Provider model."""

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=256, required=True,
                                 allow_null=False, allow_blank=False)
    type = serializers.ChoiceField(choices=Provider.PROVIDER_CHOICES)
    created_timestamp = serializers.DateTimeField(read_only=True)
    customer = CustomerSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    # pylint: disable=too-few-public-methods
    class Meta:
        """Metadata for the serializer."""

        model = Provider
        fields = ('uuid', 'name', 'type', 'authentication', 'billing_source',
                  'customer', 'created_by', 'created_timestamp')

    def __init__(self, instance=None, data=empty, **kwargs):
        """Initialize the Provider Serializer.

        Here we ensure we use the appropriate serializer to validate the
        authentication and billing_source parameters.
        """
        super().__init__(instance, data, **kwargs)

        provider_type = None
        if data and data != empty:
            provider_type = data.get('type')

        if provider_type:
            self.fields['authentication'] = AUTHENTICATION_SERIALIZERS.get(provider_type)()
            self.fields['billing_source'] = BILLING_SOURCE_SERIALIZERS.get(provider_type)(
                default={'bucket': '', 'data_source': {}}
            )
        else:
            self.fields['authentication'] = ProviderAuthenticationSerializer()
            self.fields['billing_source'] = ProviderBillingSourceSerializer()

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
            bucket = billing_source.get('bucket')
            data_source = billing_source.get('data_source', {})
        else:
            # Because of a unique together constraint, this is done
            # to allow for this field to be non-required for OCP
            # but will still have a blank no-op entry in the DB
            billing_source = {'bucket': '', 'data_source': {}}
            data_source = None

        authentication = validated_data.pop('authentication')
        provider_resource_name = authentication.get('provider_resource_name')
        credentials = authentication.get('credentials')
        provider_type = validated_data['type']
        interface = ProviderAccessor(provider_type)

        if credentials and data_source:
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
                sources_auth = {'resource_name': auth.provider_resource_name}
            elif existing_provider.type in ('AZURE', ):
                sources_auth = {'credentials': auth.credentials}
            else:
                sources_auth = {}
            source_query = Sources.objects.filter(authentication=sources_auth)
            if source_query.exists():
                source_obj = source_query.first()
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
        provider.save()
        return provider

    def update(self, instance, validated_data):
        """Update a Provider instance from validated data."""
        auth = validated_data.pop('authentication')
        bill = validated_data.pop('billing_source')

        for key in validated_data.keys():
            setattr(instance, key, validated_data[key])
        for key in auth.keys():
            setattr(instance.authentication, key, auth[key])
        for key in bill.keys():
            setattr(instance.billing_source, key, bill[key])

        instance.save()
        return instance


class AdminProviderSerializer(ProviderSerializer):
    """Provider serializer specific to service admins."""

    customer = AdminCustomerSerializer(read_only=True)
