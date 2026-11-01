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

from django.db import connection
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import APIException

from api.metrics.constants import COST_MODEL_METRIC_MAP
from api.metrics.constants import UNLEASH_METRICS_GPU
from cost_models.models import CostModelMap
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from koku.advisory_locks import AdvisoryLockTimeout
from koku.advisory_locks import lock_providers_for_transaction
from masu.processor import is_rate_sync_provider_lock_enabled

LOG = logging.getLogger(__name__)

# How long a rate change waits for RTU writers before giving up. API requests have
# about 30 s end to end (3scale), and distribution runs can hold a provider's lock
# for minutes, so waiting longer than a few seconds only ties up a Gunicorn worker.
RATE_SYNC_LOCK_TIMEOUT_MS = 5000


class RateSyncLockTimeout(APIException):
    """Rates cannot be removed right now because costs for an affected source are being recalculated."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Costs for a source that uses this price list are being recalculated. Wait a few minutes and try again."
    )
    default_code = "rate_sync_locked"


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
                raise ValueError(f"Invalid rate_id format: {rate_id}")
            if rate_uuid in existing_by_uuid:
                rate_obj = existing_by_uuid[rate_uuid]
                incoming_ids.add(rate_uuid)
                to_update.append((rate_obj, rate_data))
                used_names.add(rate_obj.custom_name)
                continue
            LOG.warning("rate_id %s not found; falling back to custom_name matching", rate_id)

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

    Deleting a Rate cascades into rates_to_usage for every provider on every
    cost model attached to the price list. Before deleting, this takes each of
    those providers' advisory lock (the one RTU writers hold) as a
    transaction-level lock, so the delete cannot interleave with a writer and
    the locks last until the caller's outermost transaction commits.
    Raises RateSyncLockTimeout (HTTP 409) if a writer holds a lock for longer
    than RATE_SYNC_LOCK_TIMEOUT_MS.
    """
    LOG.info(f"Syncing {len(rates_data)} rates to Rate table for PriceList {price_list.uuid}")
    with transaction.atomic():
        return _sync_rate_table(price_list, rates_data)


def _provider_uuids_for_price_list(price_list):
    """Return every provider whose rates_to_usage rows can reference this price list's rates."""
    cost_model_ids = PriceListCostModelMap.objects.filter(price_list=price_list).values("cost_model_id")
    return list(
        CostModelMap.objects.filter(cost_model_id__in=cost_model_ids)
        .values_list("provider_uuid", flat=True)
        .distinct()
    )


def _lock_providers_for_rate_delete(price_list):
    """Lock every provider that the stale-rate delete cascades into, or raise RateSyncLockTimeout."""
    if not is_rate_sync_provider_lock_enabled(connection.schema_name):
        return
    provider_uuids = _provider_uuids_for_price_list(price_list)
    try:
        lock_providers_for_transaction(provider_uuids, RATE_SYNC_LOCK_TIMEOUT_MS)
    except AdvisoryLockTimeout as error:
        LOG.warning(f"Not deleting stale rates of PriceList {price_list.uuid}: {error}")
        raise RateSyncLockTimeout() from error


def _sync_rate_table(price_list, rates_data):
    """Body of sync_rate_table; runs inside its transaction."""
    existing_by_uuid = {r.uuid: r for r in Rate.objects.filter(price_list=price_list)}
    existing_by_name = {r.custom_name: r for r in existing_by_uuid.values()}
    all_existing_names = set(existing_by_name.keys())

    incoming_ids, to_update, to_create_data = _classify_incoming_rates(
        rates_data, existing_by_uuid, existing_by_name, all_existing_names
    )

    to_delete_uuids = [uid for uid in existing_by_uuid if uid not in incoming_ids]
    if to_delete_uuids:
        _lock_providers_for_rate_delete(price_list)
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
