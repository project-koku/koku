#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Rate serializer."""
import logging
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal

from rest_framework import serializers

from api.common import error_obj
from api.currency.currencies import CURRENCY_CHOICES
from api.metrics import constants as metric_constants
from api.metrics.constants import SOURCE_TYPE_MAP
from api.metrics.views import CostModelMetricMapJSONException
from api.provider.models import Provider
from api.report.serializers import BaseSerializer
from api.utils import get_currency
from cost_models.cost_model_manager import CostModelException
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel

MARKUP_CHOICES = (("percent", "%"),)
TAG_RATE_ONLY = (metric_constants.OCP_NAMESPACE_MONTH,)
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


class DistributionSerializer(BaseSerializer):
    """Serializer for distribution options"""

    distribution_type = serializers.ChoiceField(
        choices=metric_constants.DISTRIBUTION_CHOICES,
        required=False,
        default=metric_constants.DEFAULT_DISTRIBUTION_TYPE,
    )
    platform_cost = serializers.BooleanField(
        required=False,
        default=metric_constants.PLATFORM_COST_DEFAULT,
    )
    worker_cost = serializers.BooleanField(
        required=False,
        default=metric_constants.WORKER_UNALLOCATED_DEFAULT,
    )
    network_unattributed = serializers.BooleanField(
        required=False,
        default=metric_constants.NETWORK_UNATTRIBUTED_DEFAULT,
    )
    storage_unattributed = serializers.BooleanField(
        required=False,
        default=metric_constants.STORAGE_UNATTRIBUTED_DEFAULT,
    )


class TieredRateSerializer(serializers.Serializer):
    """Serializer for Tiered Rate."""

    value = serializers.DecimalField(required=False, max_digits=19, decimal_places=10)
    usage = serializers.DictField(required=False)
    unit = serializers.ChoiceField(choices=CURRENCY_CHOICES)

    def validate_value(self, value):
        """Check that value is a positive value."""
        if value < 0:
            raise serializers.ValidationError("A tiered rate value must be nonnegative.")
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


class TagRateValueSerializer(serializers.Serializer):
    """Serializer for the Tag Values."""

    DECIMALS = ("value", "usage_start", "usage_end")

    tag_value = serializers.CharField(max_length=100)
    unit = serializers.ChoiceField(choices=CURRENCY_CHOICES)
    usage = serializers.DictField(required=False)
    value = serializers.DecimalField(required=False, max_digits=19, decimal_places=10)
    description = serializers.CharField(allow_blank=True, max_length=500)
    default = serializers.BooleanField()

    def validate_value(self, value):
        """Check that value is a positive value."""
        if value < 0:
            raise serializers.ValidationError("A tag rate value must be nonnegative.")

        return str(value)

    def validate_usage(self, usage):
        """Check that usage_start is a positive value."""
        usage_start = usage.get("usage_start")
        usage_end = usage.get("usage_end")
        if usage_start and usage_start < 0:
            raise serializers.ValidationError("A tag rate usage_start must be positive.")
        if usage_end and usage_end <= 0:
            raise serializers.ValidationError("A tag rate usage_end must be positive.")
        if usage_start is not None and usage_end is not None:
            if Decimal(usage_start) >= Decimal(usage_end):
                raise serializers.ValidationError("A tag rate usage_start must be less than usage_end.")
        return usage


class TagRateSerializer(serializers.Serializer):
    """Serializer for Tag Rate."""

    tag_key = serializers.CharField(max_length=100)
    tag_values = serializers.ListField()

    def validate_tag_values(self, tag_values):
        """Run validation for tag_values"""
        if tag_values == []:
            err_msg = "A tag_values can not be an empty list."
            raise serializers.ValidationError(err_msg)
        validated_rates = []
        true_defaults = []
        check_duplicate_values = []
        for tag_value in tag_values:
            serializer = TagRateValueSerializer(data=tag_value)
            serializer.is_valid(raise_exception=True)
            is_default = tag_value.get("default")
            if is_default in [True, "true", "True"]:
                true_defaults.append(is_default)
            value = tag_value.get("tag_value")
            if value in check_duplicate_values:
                err_msg = f"Duplicate tag_value ({value})."
                raise serializers.ValidationError(err_msg)
            else:
                check_duplicate_values.append(value)
            validated_rates.append(serializer.validated_data)
        if len(true_defaults) > 1:
            err_msg = "Only one tag_value per tag_key can be marked as a default."
            raise serializers.ValidationError(err_msg)
        return validated_rates

    @staticmethod
    def _convert_to_decimal(tag_value):
        for decimal_key in TagRateValueSerializer.DECIMALS:
            if decimal_key in tag_value:
                value = tag_value.get(decimal_key)
                if value:
                    tag_value[decimal_key] = Decimal(value)
            usage = tag_value.get("usage", {})
            if decimal_key in usage:
                value = usage.get(decimal_key)
                if value:
                    usage[decimal_key] = Decimal(value)
        return tag_value


class RateSerializer(serializers.Serializer):
    """Rate Serializer."""

    DECIMALS = ("value", "usage_start", "usage_end")
    RATE_TYPES = ("tiered_rates", "tag_rates")

    metric = serializers.DictField(required=True)
    cost_type = serializers.ChoiceField(choices=metric_constants.COST_TYPE_CHOICES)
    description = serializers.CharField(allow_blank=True, max_length=500, required=False)
    tiered_rates = serializers.ListField(required=False)
    tag_rates = serializers.DictField(required=False)

    @property
    def metric_map(self):
        """Return a metric map dictionary with default values."""
        metrics = metric_constants.get_cost_model_metrics_map()
        return {metric: value.get("default_cost_type") for metric, value in metrics.items()}

    @staticmethod
    def _convert_to_decimal(rate):
        for decimal_key in RateSerializer.DECIMALS:
            value = rate.get(decimal_key)
            if value:
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
                    f"usage_start of {usage_start} should be less than or equal to the"
                    f" usage_end {next_tier} of the previous tier."
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
                    f" usage_start value {usage_end} should equal to the"
                    f" usage_end value of the next tier, not {next_bucket_usage_start}."
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

    def validate_tag_rates(self, tag_rate):
        """Run validation for rates."""
        if tag_rate:
            serializer = TagRateSerializer(data=tag_rate)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        return tag_rate

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
        metric_name = data.get("metric").get("name")
        if metric_name in TAG_RATE_ONLY:
            if data.get("tiered_rates"):
                error_msg = f"{metric_name} is only available as a tag based rate."
                raise serializers.ValidationError(error_msg)
        if metric_name not in metric_constants.METRIC_CHOICES:
            error_msg = f"{metric_name} is an invalid metric"
            raise serializers.ValidationError(error_msg)

        tiered_rates = self.validate_tiered_rates(data.get("tiered_rates", []))
        tag_rates = self.validate_tag_rates(data.get("tag_rates", {}))
        if tiered_rates:
            data["tiered_rates"] = tiered_rates
        if tag_rates:
            data["tag_rates"] = tag_rates

        rate_keys_str = ", ".join(str(rate_key) for rate_key in self.RATE_TYPES)
        data["cost_type"] = self.validate_cost_type(metric_name, data.get("cost_type"))

        if any(data.get(rate_key) is not None for rate_key in self.RATE_TYPES):
            if tiered_rates == [] and tag_rates == {}:
                error_msg = f"{rate_keys_str} cannot be empty."
                raise serializers.ValidationError(error_msg)
            elif tiered_rates != [] and tag_rates != {}:
                error_msg = f"Set either '{self.RATE_TYPES[0]}' or '{self.RATE_TYPES[1]}' but not both"
                raise serializers.ValidationError(error_msg)
            elif tiered_rates is not None and tiered_rates != []:
                RateSerializer._validate_continuouse_tiers(tiered_rates)
            return data
        else:
            error_msg = f"Missing rate information: one of {rate_keys_str}"
            raise serializers.ValidationError(error_msg)

    def to_representation(self, rate_obj):
        """Create external representation of a rate."""
        out = {
            "metric": {"name": rate_obj.get("metric", {}).get("name")},
            "description": rate_obj.get("description", ""),
        }

        # Specifically handling only tiered rates now
        # with the expectation that this code will be generalized
        # when other rate types (e.g. markup) are introduced
        tiered_rates = rate_obj.get("tiered_rates", [])
        if tiered_rates:
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

        tag_rate = rate_obj.get("tag_rates", {})
        if tag_rate:
            tag_values = tag_rate.get("tag_values", [])
            for tag_value in tag_values:
                TagRateSerializer._convert_to_decimal(tag_value)
            out.update({"tag_rates": tag_rate, "cost_type": rate_obj.get("cost_type")})
        return out

    def to_internal_value(self, data):
        """Convert the JSON representation of rate to DB representation."""
        metric = data.get("metric", {})
        new_metric = {"name": metric.get("name")}
        data["metric"] = new_metric
        return data


class CostModelSerializer(BaseSerializer):
    """Serializer for a list of tiered rates."""

    class Meta:
        """Metadata for the serializer."""

        model = CostModel

    uuid = serializers.UUIDField(read_only=True)

    name = serializers.CharField(allow_blank=True, max_length=100)

    description = serializers.CharField(allow_blank=True, max_length=500)

    source_type = serializers.CharField(required=True)

    source_uuids = serializers.ListField(
        child=UUIDKeyRelatedField(queryset=Provider.objects.all(), pk_field="uuid"), required=False
    )

    created_timestamp = serializers.DateTimeField(read_only=True)

    updated_timestamp = serializers.DateTimeField(read_only=True)

    rates = RateSerializer(required=False, many=True)

    markup = MarkupSerializer(required=False)

    distribution = serializers.ChoiceField(
        choices=metric_constants.DISTRIBUTION_CHOICES, required=False, allow_blank=True
    )

    distribution_info = DistributionSerializer(required=False)

    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, required=False)

    @property
    def metric_map(self):
        """Map metrics and display names."""
        metric_map_by_source = defaultdict(dict)
        metric_map = metric_constants.get_cost_model_metrics_map()
        for metric, value in metric_map.items():
            try:
                metric_map_by_source[value["source_type"]][metric] = value
            except KeyError as e:
                LOG.error("Invalid Cost Model Metric Map", exc_info=True)
                raise CostModelMetricMapJSONException("Internal Server Error.") from e
        return metric_map_by_source

    @property
    def source_type_internal_value_map(self):
        """Map display name to internal source type."""
        internal_map = {}
        for key, value in SOURCE_TYPE_MAP.items():
            internal_map[value] = key
        return internal_map

    @staticmethod
    def _validate_one_unique_tag_key_per_metric_per_cost_type(tag_rate_list):
        """Validates that the tag rates has one unique tag_key per metric per cost_type."""
        tag_metrics = dict()
        for cost_type in metric_constants.COST_TYPE_CHOICES:
            cost_type = cost_type[0]
            tag_metrics[cost_type] = {}
        for rate in tag_rate_list:
            rate_metric_name = rate.get("metric", {}).get("name")
            rate_cost_type = rate.get("cost_type")
            rate_tag_key = rate.get("tag_rates", {}).get("tag_key")
            tag_keys = tag_metrics[rate_cost_type].get(rate_metric_name)
            err_msg = (
                f"Duplicate tag_key ({rate_tag_key}) per cost_type ({rate_cost_type}) for metric ({rate_metric_name})."
            )
            if tag_keys:
                if rate_tag_key in tag_keys:
                    raise serializers.ValidationError(err_msg)
                else:
                    tag_keys.append(rate_tag_key)
            else:
                tag_metrics[rate_cost_type][rate_metric_name] = [rate_tag_key]

    def validate(self, data):
        """Validate that the source type is acceptable."""
        # The cost model has markup, no rates, and is for a valid non-OpenShift source type
        source_type = data.get("source_type")
        if source_type and Provider.PROVIDER_CASE_MAPPING.get(source_type.lower()):
            data["source_type"] = Provider.PROVIDER_CASE_MAPPING.get(source_type.lower())

        if not data.get("currency"):
            data["currency"] = get_currency(self.context.get("request"))

        if not data.get("distribution_info"):
            # TODO: Have this return just the default distribution info after
            # QE updates tests.
            distribution_info = deepcopy(metric_constants.DEFAULT_DISTRIBUTION_INFO)
            distribution_info["distribution_type"] = data.get("distribution", metric_constants.CPU)
            data["distribution_info"] = distribution_info
        if (
            data.get("markup")
            and not data.get("rates")
            and data["source_type"] != Provider.PROVIDER_OCP
            and data["source_type"] in SOURCE_TYPE_MAP.keys()
        ):
            return data
        if data["source_type"] not in self.metric_map.keys():
            raise serializers.ValidationError("{} is not a valid source.".format(data["source_type"]))
        if data.get("rates"):
            self.validate_rates_currency(data)
        return data

    def _get_metric_display_data(self, source_type, metric):
        """Return API display metadata."""
        return self.metric_map.get(source_type, {}).get(metric)

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

    def validate_rates_currency(self, data):
        """Validate incoming currency and rates all match."""
        err_msg = "Rate units must match currency provided in a cost model."
        for rate in data.get("rates"):
            if rate and rate.get("tiered_rates"):
                for tiered_rate in rate.get("tiered_rates"):
                    if tiered_rate.get("unit") != data.get("currency"):
                        raise serializers.ValidationError(err_msg)
                    if tiered_rate.get("usage") and tiered_rate.get("usage").get("unit"):
                        if tiered_rate.get("usage").get("unit") != data.get("currency"):
                            raise serializers.ValidationError(err_msg)
            if rate and rate.get("tag_rates"):
                for tag_rate in rate.get("tag_rates").get("tag_values"):
                    if tag_rate.get("unit") != data.get("currency"):
                        raise serializers.ValidationError(err_msg)

    def validate_rates(self, rates):
        """Run validation for rates."""
        validated_rates = []
        tag_rates = []
        for rate in rates:
            serializer = RateSerializer(data=rate)
            serializer.is_valid(raise_exception=True)
            validated_rates.append(serializer.validated_data)
            if rate.get("tag_rates"):
                tag_rates.append(rate)
        if tag_rates:
            CostModelSerializer._validate_one_unique_tag_key_per_metric_per_cost_type(tag_rates)
        return validated_rates

    def validate_distribution(self, distribution):
        """Run validation for distribution choice."""
        distrib_choice_list = [choice[0] for choice in metric_constants.DISTRIBUTION_CHOICES]
        if distribution not in distrib_choice_list:
            error_msg = f"{distribution} is an invaild distribution type"
            raise serializers.ValidationError(error_msg)
        return distribution

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
        """Alter source_uuids to provider_uuids."""
        internal = super().to_internal_value(data)
        internal["provider_uuids"] = internal.get("source_uuids", [])
        return internal
