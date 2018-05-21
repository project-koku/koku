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
from rest_framework import serializers

from api.iam.models import Customer
from api.iam.serializers import (CustomerSerializer, UserSerializer)
from api.provider.models import (Provider,
                                 ProviderAuthentication,
                                 ProviderBillingSource)


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
        fields = ('__all__')


class ProviderBillingSourceSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Billing Source model."""

    uuid = serializers.UUIDField(read_only=True)
    bucket = serializers.CharField(max_length=63, required=True,
                                   allow_null=False, allow_blank=False)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderBillingSource
        fields = ('__all__')


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for the Provider  model."""

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=256, required=True,
                                 allow_null=False, allow_blank=False)
    type = serializers.CharField(max_length=50, required=False)
    authentication = ProviderAuthenticationSerializer()
    billing_source = ProviderBillingSourceSerializer()
    customer = CustomerSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        """Metadata for the serializer."""

        model = Provider
        fields = ('__all__')

    @transaction.atomic
    def create(self, validated_data):
        """Create a user from validated data."""
        authentication = validated_data.pop('authentication')
        billing_source = validated_data.pop('billing_source')

        user = None
        customer = None
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            if user.groups.count() == 1:
                group = user.groups.first()
                customer_qs = Customer.objects.filter(pk=group.id)
                if customer_qs.count() == 1:
                    customer = customer_qs.first()
                else:
                    key = 'customer'
                    message = 'Customer for requesting user could not be found.'
                    raise serializers.ValidationError(error_obj(key, message))
            else:
                key = 'customer'
                message = 'Group for requesting user could not be found.'
                raise serializers.ValidationError(error_obj(key, message))
        else:
            key = 'created_by'
            message = 'Requesting user could not be found.'
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
