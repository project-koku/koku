#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Management layer for user defined rates."""
import copy
import logging
import uuid
from datetime import date
from decimal import Decimal
from decimal import InvalidOperation

from django.db import transaction

from api.metrics.constants import COST_MODEL_METRIC_MAP
from api.metrics.constants import UNLEASH_METRICS_GPU
from api.provider.models import Provider
from api.utils import DateHelper
from common.queues import get_customer_queue
from common.queues import PriorityQueue
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from masu.processor.tasks import update_cost_model_costs

LOG = logging.getLogger(__name__)

_FULL_METRIC_MAP = {**COST_MODEL_METRIC_MAP, **UNLEASH_METRICS_GPU}

LABEL_METRIC_TO_TYPE = {
    "CPU": "cpu",
    "Memory": "memory",
    "Storage": "storage",
    "Node": "node",
    "Cluster": "cluster",
    "Persistent volume claims": "pvc",
    "Virtual Machine": "vm",
    "Project": "project",
    "GPU": "gpu",
}

CUSTOM_NAME_MAX_LENGTH = 50


def derive_metric_type(metric_name):
    """Derive a short metric type from the metric name using COST_MODEL_METRIC_MAP."""
    entry = _FULL_METRIC_MAP.get(metric_name)
    if entry:
        return LABEL_METRIC_TO_TYPE.get(entry["label_metric"], "other")
    return "other"


def generate_custom_name(rate_data, existing_names):
    """Generate a unique custom_name for a rate based on metric, cost_type, and tag_key."""
    metric_name = rate_data.get("metric", {}).get("name", "unknown")
    cost_type = rate_data.get("cost_type", "unknown")
    tag_key = rate_data.get("tag_rates", {}).get("tag_key", "") if rate_data.get("tag_rates") else ""

    if tag_key:
        base = f"{metric_name}-{cost_type}-{tag_key}"
    else:
        base = f"{metric_name}-{cost_type}"

    base = base[:CUSTOM_NAME_MAX_LENGTH]
    candidate = base
    counter = 2
    while candidate in existing_names:
        suffix = f"-{counter}"
        candidate = base[: CUSTOM_NAME_MAX_LENGTH - len(suffix)] + suffix
        counter += 1
    return candidate


def extract_default_rate(rate_data):
    """Extract the default rate value from a rate dict. Returns Decimal or None."""
    tiered_rates = rate_data.get("tiered_rates", [])
    if tiered_rates:
        first_value = tiered_rates[0].get("value")
        if first_value is not None:
            try:
                result = Decimal(str(first_value))
                if not result.is_finite():
                    return None
                return result
            except (InvalidOperation, TypeError):
                return None
    return None


class CostModelException(Exception):
    """Cost Model Manager errors."""


class CostModelManager:
    """Cost Model Manager to manage user defined cost model operations."""

    def __init__(self, cost_model_uuid=None):
        """Initialize properties for CostModelManager."""
        self._model = None
        self._cost_model_uuid = None

        if cost_model_uuid:
            try:
                self._model = CostModel.objects.get(uuid=cost_model_uuid)
                self._cost_model_uuid = cost_model_uuid
            except CostModel.DoesNotExist:
                LOG.warning(f"CostModel with UUID {cost_model_uuid} does not exist.")

    @property
    def instance(self):
        """Return the rate model instance."""
        return self._model

    @transaction.atomic
    def create(self, **data):
        """Create cost model and optionally associate to providers."""
        cost_model_data = copy.deepcopy(data)
        provider_uuids = cost_model_data.pop("provider_uuids", [])
        self._model = CostModel.objects.create(**cost_model_data)
        self.update_provider_uuids(provider_uuids)

        if self._model.rates:
            pl = self._get_or_create_price_list()
            self._sync_rate_table(pl, copy.deepcopy(data.get("rates", [])))

        return self._model

    @transaction.atomic
    def update_provider_uuids(self, provider_uuids):
        """Update rate with new provider uuids."""
        current_providers_for_instance = []
        for rate_map_instance in CostModelMap.objects.filter(cost_model=self._model):
            current_providers_for_instance.append(str(rate_map_instance.provider_uuid))

        providers_to_delete = set(current_providers_for_instance).difference(provider_uuids)
        providers_to_create = set(provider_uuids).difference(current_providers_for_instance)
        all_providers = set(current_providers_for_instance).union(provider_uuids)

        for provider_uuid in providers_to_delete:
            CostModelMap.objects.filter(provider_uuid=provider_uuid, cost_model=self._model).delete()

        for provider_uuid in providers_to_create:
            # Raise exception if source is already associated with another cost model.
            existing_cost_model = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            if existing_cost_model.exists():
                cost_model_uuid = existing_cost_model.first().cost_model.uuid
                log_msg = f"Source {provider_uuid} is already associated with cost model: {cost_model_uuid}."
                LOG.warning(log_msg)
                raise CostModelException(log_msg)
            CostModelMap.objects.create(cost_model=self._model, provider_uuid=provider_uuid)

        start_date = DateHelper().this_month_start.strftime("%Y-%m-%d")
        end_date = DateHelper().today.strftime("%Y-%m-%d")
        for provider_uuid in all_providers:
            tracing_id = uuid.uuid4()
            # Update cost-model costs for each provider, on every PUT/DELETE
            try:
                provider = Provider.objects.get(uuid=provider_uuid)
            except Provider.DoesNotExist:
                LOG.info(f"Provider {provider_uuid} does not exist. Skipping cost-model update.")
            else:
                if provider.active:
                    schema_name = provider.customer.schema_name
                    fallback_queue = get_customer_queue(schema_name, PriorityQueue)
                    # Because this is triggered from the UI, we use the priority queue
                    LOG.info(
                        f"provider {provider_uuid} update for cost model {self._cost_model_uuid} "
                        + f"with tracing_id {tracing_id}"
                    )

                    update_cost_model_costs.s(
                        schema_name,
                        provider.uuid,
                        start_date,
                        end_date,
                        tracing_id=tracing_id,
                        queue_name=fallback_queue,
                    ).set(queue=fallback_queue).apply_async()

    @transaction.atomic
    def update(self, **data):
        """Update the cost model object and sync rates to linked price list if one exists."""
        self._model.name = data.get("name", self._model.name)
        self._model.description = data.get("description", self._model.description)
        self._model.rates = data.get("rates", self._model.rates)
        self._model.markup = data.get("markup", self._model.markup)
        self._model.distribution = data.get("distribution", self._model.distribution)
        self._model.distribution_info = data.get("distribution_info", self._model.distribution_info)
        self._model.currency = data.get("currency", self._model.currency)
        self._model.save()

        if "rates" in data:
            pl = self._get_or_create_price_list()
            if pl:
                self._sync_rate_table(pl, copy.deepcopy(data.get("rates", [])))

    COST_AFFECTING_FIELDS = {"default_rate", "tag_values", "metric", "cost_type"}

    @staticmethod
    def _resolve_custom_name(rate_data, existing_names):
        """Return the custom_name for a rate, generating one if absent.

        If rate_data already contains a truthy custom_name, returns it.
        Otherwise generates a unique name via generate_custom_name() and
        stamps it onto rate_data["custom_name"] before returning.
        """
        custom_name = rate_data.get("custom_name")
        if not custom_name:
            custom_name = generate_custom_name(rate_data, existing_names)
            rate_data["custom_name"] = custom_name
        return custom_name

    @staticmethod
    def _rate_fields_from_data(rate_data, existing_names=None):
        """Extract Rate model fields from a rate data dict."""
        tag_rates = rate_data.get("tag_rates") or {}
        custom_name = CostModelManager._resolve_custom_name(rate_data, existing_names or set())
        metric_name = rate_data.get("metric", {}).get("name", "")
        cost_type = rate_data.get("cost_type", "")
        if not cost_type:
            LOG.warning(f"Rate for metric '{metric_name}' has no cost_type; storing empty string")
        return {
            "custom_name": custom_name,
            "description": rate_data.get("description", ""),
            "metric": metric_name,
            "metric_type": derive_metric_type(metric_name),
            "cost_type": cost_type,
            "default_rate": extract_default_rate(rate_data),
            "tag_key": tag_rates.get("tag_key", ""),
            "tag_values": tag_rates.get("tag_values", []),
        }

    def _apply_rate_fields(self, rate_obj, rate_data, existing_names=None):
        """Update rate_obj fields from rate_data. Returns True if any cost-affecting field changed."""
        fields = self._rate_fields_from_data(rate_data, existing_names)
        changed = False
        for attr, value in fields.items():
            if getattr(rate_obj, attr) != value:
                setattr(rate_obj, attr, value)
                if attr in self.COST_AFFECTING_FIELDS:
                    changed = True
        return changed

    def _sync_rate_table(self, price_list, rates_data):
        """Synchronize Rate table rows with the rates JSON blob using diff-based sync.

        Matches incoming rates to existing Rate rows by rate_id (UUID) first.
        If rate_id is absent, falls back to custom_name matching (backward-compat).
        If rate_id is present but does not belong to this price_list, raises CostModelException.

        Operations are ordered delete -> update -> create to avoid transient
        UniqueConstraint violations on (price_list, custom_name).
        """
        LOG.info(f"Syncing {len(rates_data)} rates to Rate table for PriceList {price_list.uuid}")
        existing_by_uuid = {r.uuid: r for r in Rate.objects.filter(price_list=price_list)}
        existing_by_name = {r.custom_name: r for r in existing_by_uuid.values()}
        all_existing_names = set(existing_by_name.keys())

        incoming_ids = set()
        to_update = []
        to_create_data = []

        for rate_data in rates_data:
            rate_id = rate_data.get("rate_id")

            if rate_id:
                try:
                    rate_uuid = uuid.UUID(str(rate_id))
                except (ValueError, AttributeError):
                    raise CostModelException(f"Invalid rate_id: {rate_id}")
                if rate_uuid not in existing_by_uuid:
                    raise CostModelException(f"Invalid rate_id: {rate_id}")
                rate_obj = existing_by_uuid[rate_uuid]
                incoming_ids.add(rate_uuid)
                to_update.append((rate_obj, rate_data))
            else:
                used_names = all_existing_names | {
                    rd.get("custom_name", "") for rd in rates_data if rd.get("custom_name")
                }
                custom_name = self._resolve_custom_name(rate_data, used_names)
                if custom_name in existing_by_name:
                    rate_obj = existing_by_name[custom_name]
                    incoming_ids.add(rate_obj.uuid)
                    to_update.append((rate_obj, rate_data))
                else:
                    to_create_data.append(rate_data)

        # Phase 1: DELETE stale rows (those not referenced by any incoming rate)
        to_delete_uuids = [uid for uid in existing_by_uuid if uid not in incoming_ids]
        if to_delete_uuids:
            deleted_count, _ = Rate.objects.filter(price_list=price_list, uuid__in=to_delete_uuids).delete()
            LOG.info(f"Deleted {deleted_count} stale Rate rows from PriceList {price_list.uuid}")

        # Phase 2: UPDATE matched rows
        for rate_obj, rate_data in to_update:
            self._apply_rate_fields(rate_obj, rate_data, all_existing_names)
            rate_obj.save()
            rate_data["rate_id"] = str(rate_obj.uuid)
            rate_data["custom_name"] = rate_obj.custom_name

        # Phase 3: CREATE new rows
        if to_create_data:
            seen_uuids = set(incoming_ids)
            rates_to_create = []
            for rate_data in to_create_data:
                fields = self._rate_fields_from_data(rate_data, all_existing_names)
                rate_uuid = uuid.uuid4()
                if rate_uuid in seen_uuids:
                    rate_uuid = uuid.uuid4()
                seen_uuids.add(rate_uuid)
                rates_to_create.append(
                    Rate(uuid=rate_uuid, price_list=price_list, **fields)
                )
                rate_data["rate_id"] = str(rate_uuid)
                rate_data["custom_name"] = fields["custom_name"]
            Rate.objects.bulk_create(rates_to_create)
            LOG.info(f"Created {len(rates_to_create)} new Rate rows for PriceList {price_list.uuid}")

        self._model.rates = rates_data
        self._model.save(update_fields=["rates"])
        price_list.rates = copy.deepcopy(rates_data)
        price_list.save(update_fields=["rates", "updated_timestamp"])

    def _get_or_create_price_list(self):
        """Get or create a PriceList linked to this CostModel. Returns the PriceList."""
        mapping = (
            PriceListCostModelMap.objects.filter(cost_model=self._model)
            .select_related("price_list")
            .order_by("priority")
            .first()
        )
        if mapping:
            return mapping.price_list

        pl = PriceList.objects.create(
            name=f"{self._model.name} prices",
            description=f"Auto-created from cost model '{self._model.name}'",
            currency=self._model.currency,
            effective_start_date=date(2026, 3, 1),
            effective_end_date=date(2099, 12, 31),
            enabled=True,
            version=1,
            rates=self._model.rates,
        )
        PriceListCostModelMap.objects.create(
            price_list=pl,
            cost_model=self._model,
            priority=1,
        )
        return pl

    def get_provider_names_uuids(self):
        """Get a list of provider uuids assoicated with rate."""
        providers_query = CostModelMap.objects.filter(cost_model=self._model)
        provider_uuids = [provider.provider_uuid for provider in providers_query]
        providers_qs_list = Provider.objects.filter(uuid__in=provider_uuids)
        provider_names_uuids = [
            {"uuid": str(provider.uuid), "name": provider.name, "last_processed": provider.data_updated_timestamp}
            for provider in providers_qs_list
        ]
        return provider_names_uuids
