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
from rest_framework.validators import UniqueValidator

from api.iam.serializers import (AdminCustomerSerializer,
                                 CustomerSerializer,
                                 UserSerializer)
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
    provider_resource_name = serializers.CharField(
        required=True, allow_null=True, allow_blank=True,
        validators=[UniqueValidator(
            queryset=ProviderAuthentication.objects.all())])

    class Meta:
        """Metadata for the serializer."""

        model = ProviderAuthentication
        fields = ('uuid', 'provider_resource_name')


class ProviderBillingSourceSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Billing Source model."""

    uuid = serializers.UUIDField(read_only=True)
    bucket = serializers.CharField(max_length=63, required=True,
                                   allow_null=False, allow_blank=True)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderBillingSource
        fields = ('uuid', 'bucket')


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for the Provider  model."""

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=256, required=True,
                                 allow_null=False, allow_blank=False)
    type = serializers.ChoiceField(choices=Provider.PROVIDER_CHOICES)
    authentication = ProviderAuthenticationSerializer()
    billing_source = ProviderBillingSourceSerializer(required=False)
    customer = CustomerSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        """Metadata for the serializer."""

        model = Provider
        fields = ('uuid', 'name', 'type', 'authentication', 'billing_source',
                  'customer', 'created_by')

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
            bucket = None

        authentication = validated_data.pop('authentication')
        provider_resource_name = authentication.get('provider_resource_name')
        provider_type = validated_data['type']
        interface = ProviderAccessor(provider_type)
        interface.cost_usage_source_ready(provider_resource_name, bucket)

        bill = None
        if bucket:
            bill = ProviderBillingSource.objects.create(**billing_source)
            bill.save()

        auth = ProviderAuthentication.objects.create(**authentication)
        auth.save()

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
