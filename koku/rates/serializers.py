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
from rates.models import Rate

CURRENCY_CHOICES = (('USD', 'USD'),)


class UUIDKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Related field to handle UUIDs."""

    def use_pk_only_optimization(self):
        """Override optimization."""
        return False

    def to_internal_value(self, data):
        """Override to_internal_value, just save uuid."""
        return data

    def to_representation(self, value):
        """Override to_representation, just show uuid."""
        if self.pk_field is not None:
            return value.uuid
        return value.pk

    def display_value(self, instance):
        """Override display_value, just show uuid."""
        return instance.uuid


class TieredRateSerializer(serializers.Serializer):
    """Serializer for Tiered Rate."""

    value = serializers.DecimalField(required=False, max_digits=19, decimal_places=10)
    usage_start = serializers.DecimalField(required=False,
                                           max_digits=19,
                                           decimal_places=10,
                                           allow_null=True)
    usage_end = serializers.DecimalField(required=False,
                                         max_digits=19,
                                         decimal_places=10,
                                         allow_null=True)
    unit = serializers.ChoiceField(choices=CURRENCY_CHOICES)

    def validate_value(self, value):
        """Check that value is a positive value."""
        if value <= 0:
            raise serializers.ValidationError('A tiered rate value must be positive.')
        return str(value)

    def validate_usage_start(self, usage_start):
        """Check that usage_start is a positive value."""
        if usage_start is None:
            return usage_start
        elif usage_start < 0:
            raise serializers.ValidationError('A tiered rate usage_start must be positive.')
        return str(usage_start)

    def validate_usage_end(self, usage_end):
        """Check that usage_end is a positive value."""
        if usage_end is None:
            return usage_end
        elif usage_end <= 0:
            raise serializers.ValidationError('A tiered rate usage_end must be positive.')
        return str(usage_end)

    def validate(self, data):
        """Validate that usage_end is greater than usage_start."""
        usage_start = data.get('usage_start')
        usage_end = data.get('usage_end')

        if usage_start is not None and usage_end is not None:
            if Decimal(usage_start) >= Decimal(usage_end):
                raise serializers.ValidationError('A tiered rate usage_start must be less than usage_end.')
            return data
        else:
            return data


class RateSerializer(serializers.ModelSerializer):
    """Rate Serializer."""

    DECIMALS = ('value', 'usage_start', 'usage_end')

    uuid = serializers.UUIDField(read_only=True)
    provider_uuid = UUIDKeyRelatedField(queryset=Provider.objects.all(), pk_field='uuid')
    metric = serializers.ChoiceField(choices=Rate.METRIC_CHOICES,
                                     required=True)
    tiered_rate = TieredRateSerializer(required=False, many=True)

    @staticmethod
    def _convert_to_decimal(rate):
        for decimal_key in RateSerializer.DECIMALS:
            if decimal_key in rate:
                value = rate.get(decimal_key)
                if value is not None:
                    decimal_value = Decimal(value)
                    rate[decimal_key] = decimal_value
        return rate

    @staticmethod
    def _validate_continuouse_tiers(tiers):
        """Validate tiers have no gaps."""
        if len(tiers) < 1:
            raise serializers.ValidationError('tiered_rate must have at least one tier.')

        sorted_tiers = sorted(tiers,
                              key=lambda tier: Decimal('-Infinity') if tier.get('usage_start') is None else Decimal(tier.get('usage_start')))  # noqa: E501
        start = sorted_tiers[0].get('usage_start')
        end = sorted_tiers[-1].get('usage_end')
        if start is not None and end is not None:
            error_msg = 'tiered_rate must have a tier with usage_start as null' \
                ' and a tier with usage_end as null.'
            raise serializers.ValidationError(error_msg)
        else:
            next_tier = None
            for tier in sorted_tiers:
                usage_start = tier.get('usage_start')
                usage_end = tier.get('usage_end')
                if (next_tier is not None and usage_start is not None
                        and Decimal(usage_start) > Decimal(next_tier)):  # noqa:W503
                    error_msg = 'tiered_rate must not have gaps between tiers.' \
                        'usage_start of {} should be less than or equal to the' \
                        ' usage_end {} of the previous tier.'.format(usage_start, next_tier)
                    raise serializers.ValidationError(error_msg)
                next_tier = usage_end

    def validate_provider_uuid(self, provider_uuid):
        """Check that provider_uuid is a valid identifier."""
        if Provider.objects.filter(uuid=provider_uuid).count() == 1:
            return provider_uuid
        else:
            raise serializers.ValidationError('Provider object does not exist with given uuid.')

    def validate(self, data):
        """Validate that a rate must be defined."""
        rate_keys = ('tiered_rate',)
        if any(data.get(rate_key) is not None for rate_key in rate_keys):
            tiered_rate = data.get('tiered_rate')
            if tiered_rate is not None:
                RateSerializer._validate_continuouse_tiers(tiered_rate)
            return data
        else:
            rate_keys_str = ', '.join(str(rate_key) for rate_key in rate_keys)
            error_msg = 'A rated must be provided (e.g. {}).'.format(rate_keys_str)
            raise serializers.ValidationError(error_msg)

    def to_representation(self, rate):
        """Create external representation of a rate."""
        rates = rate.rates
        out = {
            'uuid': rate.uuid,
            'provider_uuid': rate.provider_uuid,
            'metric': rate.metric
        }
        for rate_type in rates.values():
            if isinstance(rate_type, list):
                for rate_item in rate_type:
                    RateSerializer._convert_to_decimal(rate_item)
            else:
                RateSerializer._convert_to_decimal(rate_type)
        out.update(rates)
        return out

    def create(self, validated_data):
        """Create the rate object in the database."""
        provider_uuid = validated_data.pop('provider_uuid')
        metric = validated_data.pop('metric')
        return Rate.objects.create(provider_uuid=provider_uuid,
                                   metric=metric,
                                   rates=validated_data)

    def update(self, instance, validated_data):
        """Update the rate object in the database."""
        provider_uuid = validated_data.pop('provider_uuid')
        metric = validated_data.pop('metric')
        instance.provider_uuid = provider_uuid
        instance.metric = metric
        instance.rates = validated_data
        instance.save()
        return instance

    class Meta:
        model = Rate
        fields = ('uuid', 'provider_uuid', 'metric', 'tiered_rate')
