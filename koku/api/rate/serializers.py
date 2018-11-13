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
"""Rate serializer."""
from decimal import Decimal

from rest_framework import serializers

from api.provider.models import (Provider)
from reporting.rate.models import Rate

CURRENCY_CHOICES = (('USD', 'USD'),)


class FixedRateSerializer(serializers.Serializer):
    """Serializer for Fixed Rate."""

    value = serializers.DecimalField(required=True, max_digits=19, decimal_places=10)
    unit = serializers.ChoiceField(choices=CURRENCY_CHOICES)

    def validate_value(self, value):
        """Check that value is a positive value."""
        if value <= 0:
            raise serializers.ValidationError('A fixed rate value must be positive.')
        return str(value)


class RateSerializer(serializers.Serializer):
    """Rate Serializer."""

    uuid = serializers.UUIDField(read_only=True)
    provider = serializers.PrimaryKeyRelatedField(queryset=Provider.objects.all())
    metric = serializers.ChoiceField(choices=Rate.METRIC_CHOICES,
                                     required=True)
    fixed_rate = FixedRateSerializer()

    def to_representation(self, rate):
        """Create external representation of a rate."""
        rates = rate.rates
        out = {
            'uuid': rate.uuid,
            'provider_uuid': rate.provider_uuid,
            'metric': rate.metric
        }
        for rate_type in rates.values():
            if 'value' in rate_type:
                value = Decimal(rate_type.get('value'))
                rate_type['value'] = value
        out.update(rates)
        return out

    def create(self, validated_data):
        """Create the rate object in the database."""
        provider = validated_data.pop('provider')
        metric = validated_data.pop('metric')
        return Rate.objects.create(provider_uuid=provider.uuid,
                                   metric=metric,
                                   rates=validated_data)

    def update(self, instance, validated_data):
        """Update the rate object in the database."""
        provider = validated_data.pop('provider')
        metric = validated_data.pop('metric')
        instance.provider_uuid = provider.uuid
        instance.metric = metric
        instance.rates = validated_data
        instance.save()
        return instance
