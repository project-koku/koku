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
import copy
import logging
from collections import defaultdict
from decimal import Decimal

from rest_framework import serializers

from api.common import error_obj
from api.metrics import constants as metric_constants
from api.metrics.constants import SOURCE_TYPE_MAP
from api.metrics.views import CostModelMetricMapJSONException
from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelException
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel

CURRENCY_CHOICES = (("USD", "USD"),)
MARKUP_CHOICES = (("percent", "%"),)
LOG = logging.getLogger(__name__)


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


class MarkupSerializer(serializers.Serializer):
    """Serializer for cost markup."""

    value = serializers.DecimalField(required=False, max_digits=19, decimal_places=10, coerce_to_string=True)
    unit = serializers.ChoiceField(choices=MARKUP_CHOICES, required=False)


class TieredRateSerializer(serializers.Serializer):
    """Serializer for Tiered Rate."""

    value = serializers.DecimalField(required=False, max_digits=19, decimal_places=10)
    usage = serializers.DictField(required=False)
    unit = serializers.ChoiceField(choices=CURRENCY_CHOICES)

    def validate_value(self, value):
        """Check that value is a positive value."""
        if value <= 0:
            raise serializers.ValidationError("A tiered rate value must be positive.")
        return str(value)

    def validate_usage(self, usage):
        """Check that usage_start is a positive value."""
        usage_start = usage.get("usage_start")
        usage_end = usage.get("usage_end")

        if usage_start and usage_start < 0:
            raise serializers.ValidationError("A tiered rate usage_start must be positive.")

        if usage_end and usage_end <= 0:
            raise serializers.ValidationError("A tiered rate usage_end must be positive.")
        return usage

    def validate(self, data):
        """Validate that usage_end is greater than usage_start."""
        usage_start = data.get("usage", {}).get("usage_start")
        usage_end = data.get("usage", {}).get("usage_end")
        if usage_start is not None and usage_end is not None:
            if Decimal(usage_start) >= Decimal(usage_end):
                raise serializers.ValidationError("A tiered rate usage_start must be less than usage_end.")
            return data
        else:
            return data


class RateSerializer(serializers.Serializer):
    """Rate Serializer."""

    DECIMALS = ("value", "usage_start", "usage_end")
    RATE_TYPES = ("tiered_rates",)

    metric = serializers.DictField(required=True)
    cost_type = serializers.ChoiceField(choices=metric_constants.COST_TYPE_CHOICES)
    tiered_rates = serializers.ListField(required=False)

    @property
    def metric_map(self):
        """Return a metric map dictionary with default values."""
        metrics = copy.deepcopy(metric_constants.COST_MODEL_METRIC_MAP)
        return {metric.get("metric"): metric.get("default_cost_type") for metric in metrics}

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
    def _validate_no_tier_gaps(sorted_tiers):
        """Validate that the tiers has no gaps."""
        next_tier = None
        for tier in sorted_tiers:
            usage_start = tier.get("usage", {}).get("usage_start")
            usage_end = tier.get("usage", {}).get("usage_end")

            if (
                next_tier is not None and usage_start is not None and Decimal(usage_start) > Decimal(next_tier)
            ):  # noqa:W503
                error_msg = (
                    "tiered_rate must not have gaps between tiers."
                    "usage_start of {} should be less than or equal to the"
                    " usage_end {} of the previous tier.".format(usage_start, next_tier)
                )
                raise serializers.ValidationError(error_msg)
            next_tier = usage_end

    @staticmethod
    def _validate_no_tier_overlaps(sorted_tiers):
        """Validate that the tiers have no overlaps."""
        for i, tier in enumerate(sorted_tiers):
            next_bucket = sorted_tiers[(i + 1) % len(sorted_tiers)]
            next_bucket_usage_start = next_bucket.get("usage", {}).get("usage_start")
            usage_end = tier.get("usage", {}).get("usage_end")

            if usage_end != next_bucket_usage_start:
                error_msg = (
                    "tiered_rate must not have overlapping tiers."
                    " usage_start value {} should equal to the"
                    " usage_end value of the next tier, not {}.".format(usage_end, next_bucket_usage_start)
                )
                raise serializers.ValidationError(error_msg)

    @staticmethod
    def _validate_continuouse_tiers(tiers):
        """Validate tiers have no gaps."""
        if len(tiers) < 1:
            raise serializers.ValidationError("tiered_rate must have at least one tier.")
        sorted_tiers = sorted(
            tiers,
            key=lambda tier: (
                Decimal("-Infinity")
                if tier.get("usage", {}).get("usage_start") is None
                else Decimal(tier.get("usage", {}).get("usage_start"))
            ),
        )
        start = sorted_tiers[0].get("usage", {}).get("usage_start")
        end = sorted_tiers[-1].get("usage", {}).get("usage_end")

        if start is not None or end is not None:
            error_msg = "tiered_rate must have a tier with usage_start as null and a tier with usage_end as null."
            raise serializers.ValidationError(error_msg)
        else:
            RateSerializer._validate_no_tier_gaps(sorted_tiers)
            RateSerializer._validate_no_tier_overlaps(sorted_tiers)

    def validate_tiered_rates(self, tiered_rates):
        """Force validation of tiered rates."""
        validated_rates = []
        for rate in tiered_rates:
            serializer = TieredRateSerializer(data=rate)
            serializer.is_valid(raise_exception=True)
            validated_rates.append(serializer.validated_data)
        return validated_rates

    def validate_cost_type(self, metric, cost_type):
        """Force validation of cost_type."""
        choices = {choice.lower(): choice for choice in self.get_fields().get("cost_type").choices}
        if cost_type is None:
            cost_type = self.metric_map.get(metric)
        if cost_type.lower() not in choices:
            error_msg = f"{cost_type} is an invalid cost type"
            raise serializers.ValidationError(error_msg)
        cost_type = choices[cost_type.lower()]
        return cost_type

    def validate(self, data):
        """Validate that a rate must be defined."""
        data["tiered_rates"] = self.validate_tiered_rates(data.get("tiered_rates", []))

        rate_keys_str = ", ".join(str(rate_key) for rate_key in self.RATE_TYPES)
        if data.get("metric").get("name") not in [metric for metric, metric2 in metric_constants.METRIC_CHOICES]:
            error_msg = "{} is an invalid metric".format(data.get("metric").get("name"))
            raise serializers.ValidationError(error_msg)

        data["cost_type"] = self.validate_cost_type(data.get("metric").get("name"), data.get("cost_type"))

        if any(data.get(rate_key) is not None for rate_key in self.RATE_TYPES):
            tiered_rates = data.get("tiered_rates")
            if tiered_rates == []:
                error_msg = f"A rate must be provided (e.g. {rate_keys_str})."
                raise serializers.ValidationError(error_msg)
            elif tiered_rates is not None:
                RateSerializer._validate_continuouse_tiers(tiered_rates)
            return data
        else:
            error_msg = f"A rate must be provided (e.g. {rate_keys_str})."
            raise serializers.ValidationError(error_msg)

    def to_representation(self, rate_obj):
        """Create external representation of a rate."""
        out = {"metric": {"name": rate_obj.get("metric", {}).get("name")}}

        # Specifically handling only tiered rates now
        # with the expectation that this code will be generalized
        # when other rate types (e.g. markup) are introduced
        tiered_rates = rate_obj.get("tiered_rates", [])

        for rates in tiered_rates:
            if isinstance(rates, list):
                for rate in rates:
                    RateSerializer._convert_to_decimal(rate)
                    if not rate.get("usage"):
                        rate["usage"] = {
                            "usage_start": rate.pop("usage_start", None),
                            "usage_end": rate.pop("usage_end", None),
                            "unit": rate.get("unit"),
                        }
            else:
                RateSerializer._convert_to_decimal(rates)
                if not rates.get("usage"):
                    rates["usage"] = {
                        "usage_start": rates.pop("usage_start", None),
                        "usage_end": rates.pop("usage_end", None),
                        "unit": rates.get("unit"),
                    }

        out.update({"tiered_rates": tiered_rates, "cost_type": rate_obj.get("cost_type")})
        return out

    def to_internal_value(self, data):
        """Convert the JSON representation of rate to DB representation."""
        metric = data.get("metric", {})
        new_metric = {"name": metric.get("name")}
        data["metric"] = new_metric
        return data


class CostModelSerializer(serializers.Serializer):
    """Serializer for a list of tiered rates."""

    class Meta:
        """Metadata for the serializer."""

        model = CostModel

    uuid = serializers.UUIDField(read_only=True)

    name = serializers.CharField(allow_blank=True)

    description = serializers.CharField(allow_blank=True)

    source_type = serializers.CharField(required=True)

    source_uuids = serializers.ListField(
        child=UUIDKeyRelatedField(queryset=Provider.objects.all(), pk_field="uuid"), required=False
    )

    created_timestamp = serializers.DateTimeField(read_only=True)

    updated_timestamp = serializers.DateTimeField(read_only=True)

    rates = RateSerializer(required=False, many=True)

    markup = MarkupSerializer(required=False)

    @property
    def metric_map(self):
        """Map metrics and display names."""
        metric_map_by_source = defaultdict(dict)
        metric_map = copy.deepcopy(metric_constants.COST_MODEL_METRIC_MAP)
        for metric in metric_map:
            try:
                metric_map_by_source[metric.get("source_type")][metric.get("metric")] = metric
            except TypeError:
                LOG.error("Invalid Cost Model Metric Map", exc_info=True)
                raise CostModelMetricMapJSONException("Internal Server Error.")
        return metric_map_by_source

    @property
    def source_type_internal_value_map(self):
        """Map display name to internal source type."""
        internal_map = {}
        for key, value in SOURCE_TYPE_MAP.items():
            internal_map[value] = key
        return internal_map

    def validate(self, data):
        """Validate that the source type is acceptable."""
        # The cost model has markup, no rates, and is for a valid non-OpenShift source type
        source_type = data.get("source_type")
        if source_type and Provider.PROVIDER_CASE_MAPPING.get(source_type.lower()):
            data["source_type"] = Provider.PROVIDER_CASE_MAPPING.get(source_type.lower())

        if (
            data.get("markup")
            and not data.get("rates")
            and data["source_type"] != Provider.PROVIDER_OCP
            and data["source_type"] in SOURCE_TYPE_MAP.keys()
        ):
            return data
        if data["source_type"] not in self.metric_map.keys():
            raise serializers.ValidationError("{} is not a valid source.".format(data["source_type"]))
        return data

    def _get_metric_display_data(self, source_type, metric):
        """Return API display metadata."""
        return self.metric_map.get(source_type, {}).get(metric)

    def _check_for_duplicate_metrics(self, rates):
        """Check for duplicate metric/rate combinations within a cost model."""
        rate_type_by_metric = defaultdict(dict)
        for rate in rates:
            metric = rate.get("metric", {}).get("name")
            for key in rate:
                if key in RateSerializer.RATE_TYPES:
                    if key in rate_type_by_metric[metric]:
                        rate_type_by_metric[metric][key] += 1
                    else:
                        rate_type_by_metric[metric][key] = 1
        for metric in rate_type_by_metric:
            for rate_type, count in rate_type_by_metric[metric].items():
                if count > 1:
                    err_msg = f"Duplicate {rate_type} entry found for {metric}"
                    raise serializers.ValidationError(err_msg)

    def validate_source_uuids(self, source_uuids):
        """Check that uuids in source_uuids are valid identifiers."""
        valid_uuids = []
        invalid_uuids = []
        for uuid in source_uuids:
            if Provider.objects.filter(uuid=uuid).count() == 1:
                valid_uuids.append(uuid)
            else:
                invalid_uuids.append(uuid)
        if invalid_uuids:
            err_msg = f"Provider object does not exist with following uuid(s): {invalid_uuids}."
            raise serializers.ValidationError(err_msg)
        return valid_uuids

    def validate_rates(self, rates):
        """Run validation for rates."""
        self._check_for_duplicate_metrics(rates)
        validated_rates = []
        for rate in rates:
            serializer = RateSerializer(data=rate)
            serializer.is_valid(raise_exception=True)
            validated_rates.append(serializer.validated_data)
        return validated_rates

    def create(self, validated_data):
        """Create the cost model object in the database."""
        source_uuids = validated_data.pop("source_uuids", [])
        validated_data.update({"provider_uuids": source_uuids})
        try:
            return CostModelManager().create(**validated_data)
        except CostModelException as error:
            raise serializers.ValidationError(error_obj("cost-models", str(error)))

    def update(self, instance, validated_data, *args, **kwargs):
        """Update the rate object in the database."""
        source_uuids = validated_data.pop("source_uuids", [])
        new_providers_for_instance = []
        for uuid in source_uuids:
            new_providers_for_instance.append(str(Provider.objects.filter(uuid=uuid).first().uuid))
        try:
            manager = CostModelManager(cost_model_uuid=instance.uuid)
            manager.update_provider_uuids(new_providers_for_instance)
            manager.update(**validated_data)
        except CostModelException as error:
            raise serializers.ValidationError(error_obj("cost-models", str(error)))
        return manager.instance

    def to_representation(self, cost_model_obj):
        """Add provider UUIDs to the returned model."""
        rep = super().to_representation(cost_model_obj)
        rates = rep["rates"]
        for rate in rates:
            metric = rate.get("metric", {})
            display_data = self._get_metric_display_data(cost_model_obj.source_type, metric.get("name"))
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
        rep["rates"] = rates

        source_type = rep.get("source_type")
        if source_type in SOURCE_TYPE_MAP:
            source_type = SOURCE_TYPE_MAP[source_type]
        rep["source_type"] = source_type

        rep["source_uuids"] = rep.get("provider_uuids", [])
        if rep.get("provider_uuids"):
            del rep["provider_uuids"]
        cm_uuid = cost_model_obj.uuid
        source_uuids = CostModelManager(cm_uuid).get_provider_names_uuids()
        rep.update({"sources": source_uuids})
        return rep

    def to_internal_value(self, data):
        """ Alter source_uuids to provider_uuids."""
        internal = super().to_internal_value(data)
        internal["provider_uuids"] = internal.get("source_uuids", [])
        return internal
