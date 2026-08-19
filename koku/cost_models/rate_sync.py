#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Shared Rate table synchronization logic for CostModel and PriceList managers."""
import copy
import logging
import uuid
from contextlib import contextmanager
from contextlib import ExitStack
from decimal import Decimal
from decimal import InvalidOperation

from django.db import connection
from django.db import transaction

from api.metrics.constants import COST_MODEL_METRIC_MAP
from api.metrics.constants import UNLEASH_METRICS_GPU
from cost_models.models import CostModelMap
from cost_models.models import PriceListCostModelMap
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


@contextmanager
def _provider_distribution_lock(provider_uuid):
    """Acquire the same session-scoped advisory lock used by the RTU write/delete paths.

    Keyed identically (pg_advisory_lock(hashtext(str(provider_uuid)))) to
    OCPReportDBAccessor._distribution_provider_lock and Provider's own copy of
    this primitive, so this serializes against every RTU write step and
    against Provider.delete() for the same provider, without needing a shared
    import between the masu, api, and cost_models apps.
    """
    lock_key = str(provider_uuid)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [lock_key])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [lock_key])


@contextmanager
def _multi_provider_distribution_lock(provider_uuids):
    """Hold _provider_distribution_lock for every provider_uuid at once, in sorted order.

    Sorting avoids a lock-ordering deadlock if two concurrent callers each try
    to lock an overlapping set of providers in different orders (e.g. two
    price lists that are each shared across two overlapping cost models).
    """
    with ExitStack() as stack:
        for provider_uuid in sorted(set(map(str, provider_uuids))):
            stack.enter_context(_provider_distribution_lock(provider_uuid))
        yield


def _provider_uuids_for_price_list(price_list):
    """Resolve every provider_uuid reachable from a price list via its cost models.

    A price list can be attached (PriceListCostModelMap) to multiple cost
    models, each of which can be attached (CostModelMap) to multiple
    providers. This is the full blast radius of rates_to_usage rows that
    sync_rate_table's stale-Rate cleanup can cascade-delete for a single
    price list edit.
    """
    cost_model_ids = PriceListCostModelMap.objects.filter(price_list=price_list).values_list(
        "cost_model_id", flat=True
    )
    return list(
        CostModelMap.objects.filter(cost_model_id__in=list(cost_model_ids)).values_list("provider_uuid", flat=True)
    )


def sync_rate_table(price_list, rates_data):
    """Synchronize Rate table rows with the rates JSON blob using diff-based sync.

    Operations are ordered delete -> update -> create to avoid transient
    UniqueConstraint violations on (price_list, custom_name).

    Enriches rates_data in-place with rate_id and custom_name, and updates
    price_list.rates with the enriched copy.

    Returns the enriched rates_data list.

    COST-7249 deadlock preflight, Finding E: the stale-Rate delete below
    cascades (Rate -> RatesToUsage, on_delete=CASCADE) into rates_to_usage
    rows for every provider on every cost model attached to this price list --
    not just one provider's report period. Locking here, at the single shared
    choke point all five call sites (CostModelManager.create/update,
    PriceListManager.create/update, PriceListViewSet._ensure_rate_sync) funnel
    through, guarantees the fix can't be bypassed by a new call site later.
    Spiked empirically: see
    masu/test/database/test_cost_model_rate_delete_rtu_race.py.

    Broader deadlock preflight, Finding G: CostModelManager.create/update
    (two of the five call sites above) are @transaction.atomic, and
    PriceListViewSet._ensure_rate_sync wraps its own call in transaction.atomic()
    too -- so this function can run inside an already-open transaction. The
    inner transaction.atomic() below is required, not decorative: it gives
    Postgres a rollback boundary (a savepoint, when nested) so a DB-level
    error raised by the body below is fully rolled back *before* the lock's
    own `finally: pg_advisory_unlock(...)` runs. Without it, the unlock
    statement would itself execute against an already-aborted transaction,
    fail, and leak the session-scoped advisory lock on that connection until
    it's closed -- exactly how Provider.delete() already guards its own
    cascade (see api/provider/models.py). Spiked empirically: see
    masu/test/database/test_sync_rate_table_lock_leak.py.
    """
    LOG.info(f"Syncing {len(rates_data)} rates to Rate table for PriceList {price_list.uuid}")
    provider_uuids = _provider_uuids_for_price_list(price_list)
    with _multi_provider_distribution_lock(provider_uuids), transaction.atomic():
        return _sync_rate_table_locked(price_list, rates_data)


def _sync_rate_table_locked(price_list, rates_data):
    """Body of sync_rate_table, run while holding _multi_provider_distribution_lock."""
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
