#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for Price List API."""
import logging

from rest_framework import serializers

from api.report.serializers import BaseSerializer
from cost_models.models import PriceList
from cost_models.price_list_manager import PriceListException
from cost_models.price_list_manager import PriceListManager
from cost_models.serializers import CostModelSerializer
from cost_models.serializers import RateSerializer

LOG = logging.getLogger(__name__)


class PriceListSerializer(BaseSerializer):
    """Serializer for PriceList."""

    class Meta:
        model = PriceList

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    currency = serializers.CharField(required=False)
    effective_start_date = serializers.DateField(required=False)
    effective_end_date = serializers.DateField(required=False)
    enabled = serializers.BooleanField(required=False)
    version = serializers.IntegerField(read_only=True)
    rates = RateSerializer(many=True, required=False)
    created_timestamp = serializers.DateTimeField(read_only=True)
    updated_timestamp = serializers.DateTimeField(read_only=True)

    def validate_rates(self, rates):
        """Validate rates — reuse CostModelSerializer's tag key uniqueness check."""
        tag_rates = [rate for rate in rates if rate.get("tag_rates")]
        if tag_rates:
            CostModelSerializer._validate_one_unique_tag_key_per_metric_per_cost_type(tag_rates)
        return rates

    def validate(self, data):
        """Validate that effective_end_date is after effective_start_date."""
        start = data.get("effective_start_date")
        end = data.get("effective_end_date")

        if self.instance:
            start = start or self.instance.effective_start_date
            end = end or self.instance.effective_end_date

        if start and end and end < start:
            raise serializers.ValidationError("effective_end_date must be on or after effective_start_date.")

        if data.get("rates"):
            CostModelSerializer.validate_rates_currency(data)

        return data

    def create(self, validated_data):
        """Create a price list via the manager."""
        try:
            manager = PriceListManager()
            return manager.create(**validated_data)
        except PriceListException as error:
            raise serializers.ValidationError(str(error))

    def update(self, instance, validated_data):
        """Update a price list via the manager."""
        try:
            manager = PriceListManager(instance.uuid)
            return manager.update(**validated_data)
        except PriceListException as error:
            raise serializers.ValidationError(str(error))
