#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Shared Rate table synchronization logic for CostModel and PriceList managers."""
import copy
import logging
import uuid
from decimal import Decimal
from decimal import InvalidOperation

from api.metrics.constants import COST_MODEL_METRIC_MAP
from api.metrics.constants import UNLEASH_METRICS_GPU
from cost_models.models import Rate

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


def _resolve_custom_name(rate_data, existing_names):
    """Return the custom_name for a rate, generating one if absent."""
    custom_name = rate_data.get("custom_name")
    if not custom_name:
        custom_name = generate_custom_name(rate_data, existing_names)
        rate_data["custom_name"] = custom_name
    return custom_name


def _rate_fields_from_data(rate_data, existing_names=None):
    """Extract Rate model fields from a rate data dict."""
    tag_rates = rate_data.get("tag_rates") or {}
    custom_name = _resolve_custom_name(rate_data, existing_names or set())
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


COST_AFFECTING_FIELDS = {"default_rate", "tag_values", "metric", "cost_type"}

_RATE_UPDATE_FIELDS = [
    "custom_name",
    "description",
    "metric",
    "metric_type",
    "cost_type",
    "default_rate",
    "tag_key",
    "tag_values",
]


def _apply_rate_fields(rate_obj, rate_data, existing_names=None):
    """Update rate_obj fields from rate_data. Returns True if any cost-affecting field changed."""
    fields = _rate_fields_from_data(rate_data, existing_names)
    changed = False
    for attr, value in fields.items():
        if getattr(rate_obj, attr) != value:
            setattr(rate_obj, attr, value)
            if attr in COST_AFFECTING_FIELDS:
                changed = True
    return changed


def _classify_incoming_rates(rates_data, existing_by_uuid, existing_by_name, all_existing_names):
    """Classify each incoming rate as update-existing or create-new.

    Returns (incoming_ids, to_update, to_create_data).
    Raises ValueError for invalid rate_id references.
    """
    incoming_ids = set()
    to_update = []
    to_create_data = []

    used_names = all_existing_names | {rd.get("custom_name", "") for rd in rates_data if rd.get("custom_name")}

    for rate_data in rates_data:
        rate_id = rate_data.get("rate_id")

        if rate_id:
            try:
                rate_uuid = uuid.UUID(str(rate_id))
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid rate_id: {rate_id}")
            if rate_uuid not in existing_by_uuid:
                raise ValueError(f"Invalid rate_id: {rate_id}")
            rate_obj = existing_by_uuid[rate_uuid]
            incoming_ids.add(rate_uuid)
            to_update.append((rate_obj, rate_data))
        else:
            custom_name = _resolve_custom_name(rate_data, used_names)
            used_names.add(custom_name)
            if custom_name in existing_by_name:
                rate_obj = existing_by_name[custom_name]
                incoming_ids.add(rate_obj.uuid)
                to_update.append((rate_obj, rate_data))
            else:
                to_create_data.append(rate_data)

    return incoming_ids, to_update, to_create_data


def sync_rate_table(price_list, rates_data):
    """Synchronize Rate table rows with the rates JSON blob using diff-based sync.

    Operations are ordered delete -> update -> create to avoid transient
    UniqueConstraint violations on (price_list, custom_name).

    Enriches rates_data in-place with rate_id and custom_name, and updates
    price_list.rates with the enriched copy.

    Returns the enriched rates_data list.
    """
    LOG.info(f"Syncing {len(rates_data)} rates to Rate table for PriceList {price_list.uuid}")
    existing_by_uuid = {r.uuid: r for r in Rate.objects.filter(price_list=price_list)}
    existing_by_name = {r.custom_name: r for r in existing_by_uuid.values()}
    all_existing_names = set(existing_by_name.keys())

    incoming_ids, to_update, to_create_data = _classify_incoming_rates(
        rates_data, existing_by_uuid, existing_by_name, all_existing_names
    )

    to_delete_uuids = [uid for uid in existing_by_uuid if uid not in incoming_ids]
    if to_delete_uuids:
        deleted_count, _ = Rate.objects.filter(price_list=price_list, uuid__in=to_delete_uuids).delete()
        LOG.info(f"Deleted {deleted_count} stale Rate rows from PriceList {price_list.uuid}")

    for rate_obj, rate_data in to_update:
        _apply_rate_fields(rate_obj, rate_data, all_existing_names)
        rate_data["rate_id"] = str(rate_obj.uuid)
        rate_data["custom_name"] = rate_obj.custom_name
    if to_update:
        Rate.objects.bulk_update([obj for obj, _ in to_update], _RATE_UPDATE_FIELDS)

    if to_create_data:
        seen_uuids = set(incoming_ids)
        rates_to_create = []
        for rate_data in to_create_data:
            fields = _rate_fields_from_data(rate_data, all_existing_names)
            rate_uuid = uuid.uuid4()
            while rate_uuid in seen_uuids:
                rate_uuid = uuid.uuid4()
            seen_uuids.add(rate_uuid)
            rates_to_create.append(Rate(uuid=rate_uuid, price_list=price_list, **fields))
            rate_data["rate_id"] = str(rate_uuid)
            rate_data["custom_name"] = fields["custom_name"]
        Rate.objects.bulk_create(rates_to_create)
        LOG.info(f"Created {len(rates_to_create)} new Rate rows for PriceList {price_list.uuid}")

    price_list.rates = copy.deepcopy(rates_data)
    price_list.save(update_fields=["rates", "updated_timestamp"])

    return rates_data
