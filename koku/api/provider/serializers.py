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

from django.db import transaction
from django.utils.translation import ugettext as _
from providers.provider_access import ProviderAccessor
from rest_framework import serializers

from api.iam.serializers import (AdminCustomerSerializer,
                                 CustomerSerializer,
                                 UserSerializer)
from api.provider.models import (Provider,
                                 ProviderAuthentication,
                                 ProviderBillingSource)
from api.report.serializers import StringOrListField


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
    provider_resource_name = serializers.CharField(
        required=True, allow_null=True, allow_blank=True)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderAuthentication
        fields = ('uuid', 'provider_resource_name')


class ProviderBillingSourceSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Billing Source model."""

    uuid = serializers.UUIDField(read_only=True)
    bucket = StringOrListField(max_length=63, required=True,
                               allow_null=False)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderBillingSource
        fields = ('uuid', 'bucket')


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for the Provider model."""

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=256, required=True,
                                 allow_null=False, allow_blank=False)
    type = serializers.ChoiceField(choices=Provider.PROVIDER_CHOICES)
    created_timestamp = serializers.DateTimeField(read_only=True)
    authentication = ProviderAuthenticationSerializer()
    billing_source = ProviderBillingSourceSerializer(default={'bucket': ''})
    customer = CustomerSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        """Metadata for the serializer."""

        model = Provider
        fields = ('uuid', 'name', 'type', 'authentication', 'billing_source',
                  'customer', 'created_by', 'created_timestamp')

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
        else:
            # Because of a unique together constraint, this is done
            # to allow for this field to be non-required for OCP
            # but will still have a blank no-op entry in the DB
            billing_source = {'bucket': ''}
        authentication = validated_data.pop('authentication')
        provider_resource_name = authentication.get('provider_resource_name')
        provider_type = validated_data['type']
        interface = ProviderAccessor(provider_type)
        interface.cost_usage_source_ready(provider_resource_name, bucket)

        bill, __ = ProviderBillingSource.objects.get_or_create(**billing_source)

        auth, __ = ProviderAuthentication.objects.get_or_create(**authentication)

        # We can re-use a billing source or a auth, but not the same combination.
        unique_count = Provider.objects.filter(authentication=auth)\
            .filter(billing_source=bill).count()
        if unique_count != 0:
            error = {'Error': 'A Provider already exists with that Authentication and Billing Source'}
            raise serializers.ValidationError(error)

        provider = Provider.objects.create(**validated_data)
        provider.customer = customer
        provider.created_by = user
        provider.authentication = auth
        provider.billing_source = bill
        provider.save()
        return provider


class AdminProviderSerializer(ProviderSerializer):
    """Provider serializer specific to service admins."""

    customer = AdminCustomerSerializer(read_only=True)
