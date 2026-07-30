#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for Price List API."""
import logging
from datetime import timedelta

from rest_framework import serializers

from api.common import error_obj
from api.currency.currencies import CurrencyField
from api.metrics import constants as metric_constants
from api.metrics.views import CostModelMetricMapJSONException
from api.provider.models import Provider
from api.report.serializers import BaseSerializer
from api.utils import get_currency
from cost_models.models import PriceList
from cost_models.price_list_manager import PriceListException
from cost_models.price_list_manager import PriceListManager
from cost_models.serializers import CostModelSerializer
from cost_models.serializers import RateSerializer
from masu.processor import is_cost_model_writes_disabled

LOG = logging.getLogger(__name__)


class PriceListSerializer(BaseSerializer):
    """Serializer for PriceList."""

    class Meta:
        model = PriceList

    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    currency = CurrencyField(required=False, enabled_only=True)
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
        seen = set()
        dupes = set()
        for r in rates:
            name = r.get("custom_name")
            if name:
                if name in seen:
                    dupes.add(name)
                seen.add(name)
        if dupes:
            raise serializers.ValidationError(
                f"Duplicate custom_name values in a single request are not allowed: {sorted(dupes)}"
            )
        return rates

    @staticmethod
    def _validate_dates(start, end):
        if start and start.day != 1:
            raise serializers.ValidationError("effective_start_date must be on the first day of the month.")
        if end:
            next_day = end + timedelta(days=1)
            if next_day.day != 1:
                raise serializers.ValidationError("effective_end_date must be on the last day of the month.")
        if start and end and end < start:
            raise serializers.ValidationError("effective_end_date must be on or after effective_start_date.")

    def validate(self, data):
        """Validate price list data."""
        if not self.instance:
            errors = {}
            for field in ("name", "effective_start_date", "effective_end_date"):
                if not data.get(field):
                    errors[field] = "This field is required."
            if errors:
                raise serializers.ValidationError(errors)

        start = data.get("effective_start_date")
        end = data.get("effective_end_date")

        if self.instance:
            start = start or self.instance.effective_start_date
            end = end or self.instance.effective_end_date
            if "currency" not in data:
                data["currency"] = self.instance.currency

        self._validate_dates(start, end)

        if not data.get("currency"):
            data["currency"] = get_currency(self.context.get("request"))

        if data.get("rates"):
            CostModelSerializer.validate_rates_currency(data)

        return data

    def _check_write_freeze(self):
        """Raise ValidationError if rate data writes are frozen for migration."""
        customer = self.customer if hasattr(self, "customer") else None
        schema = customer.schema_name if customer else None
        if schema and is_cost_model_writes_disabled(schema):
            raise serializers.ValidationError(
                error_obj(
                    "price-lists",
                    "Price list writes are temporarily disabled during migration.",
                )
            )

    def create(self, validated_data):
        """Create a price list via the manager."""
        self._check_write_freeze()
        try:
            manager = PriceListManager()
            return manager.create(**validated_data)
        except PriceListException as error:
            raise serializers.ValidationError(str(error))

    def update(self, instance, validated_data):
        """Update a price list via the manager."""
        self._check_write_freeze()
        try:
            manager = PriceListManager(instance.uuid)
            return manager.update(**validated_data)
        except PriceListException as error:
            raise serializers.ValidationError(str(error))

    def duplicate(self, instance):
        """Duplicate a price list via the manager."""
        self._check_write_freeze()
        try:
            manager = PriceListManager(instance.uuid)
            return manager.duplicate()
        except PriceListException as error:
            raise serializers.ValidationError(str(error))

    def to_representation(self, instance):
        """Add assigned cost model data and metric display labels to the response."""
        rep = super().to_representation(instance)
        if rep.get("rates"):
            schema = None
            request = self.context.get("request")
            if request and hasattr(request, "user") and hasattr(request.user, "customer"):
                schema = request.user.customer.schema_name
            metric_map = metric_constants.get_cost_model_metrics_map(schema=schema)
            source_type = Provider.PROVIDER_OCP
            metric_map_by_source = {k: v for k, v in metric_map.items() if v.get("source_type") == source_type}
            for rate in rep["rates"]:
                metric = rate.get("metric", {})
                display_data = metric_map_by_source.get(metric.get("name"))
                try:
                    metric.update(
                        {
                            "label_metric": display_data["label_metric"],
                            "label_measurement": display_data["label_measurement"],
                            "label_measurement_unit": display_data["label_measurement_unit"],
                        }
                    )
                except (KeyError, TypeError):
                    LOG.error("Invalid Cost Model Metric Map", exc_info=True)
                    raise CostModelMetricMapJSONException("Internal Error.")
        rep["assigned_cost_model_count"] = (
            instance.assigned_cost_model_count
            if hasattr(instance, "assigned_cost_model_count")
            else instance.cost_model_maps.count()
        )
        rep["assigned_cost_models"] = [
            {"uuid": str(m.cost_model.uuid), "name": m.cost_model.name, "priority": m.priority}
            for m in instance.cost_model_maps.all()
        ]
        return rep
