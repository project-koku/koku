"""Two-level cache for the Sources list API."""
import copy
import hashlib
import json
import logging
import time
from datetime import datetime
from datetime import timezone

from django.conf import settings
from django.core.cache import caches
from django_tenants.utils import schema_context
from prometheus_client import Counter
from prometheus_client import Histogram

from api.provider.provider_manager import bulk_source_details
from api.provider.provider_manager import unlinked_source_details
from koku.settings import CacheEnum
from sources.cache_events import get_generation

LOG = logging.getLogger(__name__)
SOURCES_CACHE_READS = Counter("sources_list_cache_reads_total", "Sources list cache read outcomes", ["outcome"])
SOURCES_CACHE_FILLED_SECONDS = Histogram(
    "sources_list_cache_fill_seconds", "Sources list cache fill duration", ["layer"]
)


def _ttl():
    now = datetime.now(timezone.utc)
    next_month = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    return min(settings.CACHE_MIDDLEWARE_SECONDS, (next_month - now).total_seconds())


def _page_key(request, schema):
    user = request.user
    dimensions = {
        "url": request.get_full_path(),
        "accept": request.META.get("HTTP_ACCEPT", ""),
        "renderer": request.accepted_renderer.format,
        "user": str(user.uuid),
        "admin": bool(user.admin),
        "access": user.access,
    }
    digest = hashlib.sha256(json.dumps(dimensions, sort_keys=True, default=str).encode()).hexdigest()
    return f"sources:snapshot:v3:{schema}:{digest}"


def _detail_key(schema, provider_uuid, generation):
    now = datetime.now(timezone.utc)
    return f"sources:detail:{schema}:{provider_uuid}:{generation}:{now.year}-{now.month}"


def _wait_for_fill(cache, key, accept=lambda value: True, timeout=0.3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.015)
        value = cache.get(key)
        if value is not None and accept(value):
            return value
    return None


def _generation_keys(schema, uuids):
    return [f"sources:gen:{schema}:page", *(f"sources:gen:{schema}:provider:{uuid}" for uuid in uuids)]


def _generations(cache, schema, uuids):
    keys = _generation_keys(schema, uuids)
    values = cache.get_many(keys)
    for key in keys:
        if key not in values:
            scope = key.removeprefix(f"sources:gen:{schema}:")
            generation = get_generation(schema, scope)
            if generation is None:
                raise RuntimeError("Unable to initialize sources cache generation")
            values[key] = generation
    return [values[key] for key in keys]


def _assemble(base, details, strip_secret):
    data = copy.deepcopy(base)
    for source in data["data"]:
        strip_secret(source)
        source.update(details.get(str(source["uuid"])) or unlinked_source_details())
    return data


def _snapshot_result(snapshot):
    return snapshot["response"], snapshot["rendered"]


def _refresh_snapshot(cache, key, schema, snapshot, tenant_generation, lookup_details, render):
    """Patch changed providers, or signal that the source page needs a rebuild."""
    uuids = [str(item["uuid"]) for item in snapshot["response"]["data"]]
    generations = _generations(cache, schema, uuids)
    if generations == snapshot["generations"]:
        SOURCES_CACHE_READS.labels("epoch_only").inc()
        snapshot["tenant_generation"] = tenant_generation
        cache.set(key, snapshot, timeout=_ttl())
        return _snapshot_result(snapshot)
    if generations[0] != snapshot["generations"][0]:
        return None

    fill_started = time.monotonic()
    changed = [
        uuid for index, uuid in enumerate(uuids) if generations[index + 1] != snapshot["generations"][index + 1]
    ]
    details = lookup_details(changed)
    response = copy.deepcopy(snapshot["response"])
    detail_fields = unlinked_source_details().keys()
    for index, uuid in enumerate(uuids):
        if uuid in details:
            source = response["data"][index]
            for field in detail_fields:
                source.pop(field, None)
            source.update(details[uuid])
    rendered = render(response)
    SOURCES_CACHE_FILLED_SECONDS.labels("provider_patch").observe(time.monotonic() - fill_started)
    SOURCES_CACHE_READS.labels("provider_patch").inc()
    if get_generation(schema, "tenant") == tenant_generation and _generations(cache, schema, uuids) == generations:
        cache.set(
            key,
            {
                **snapshot,
                "tenant_generation": tenant_generation,
                "generations": generations,
                "response": response,
                "rendered": rendered,
            },
            timeout=_ttl(),
        )
    return response, rendered


def _build_snapshot(cache, key, schema, tenant_generation, build_page, lookup_details, strip_secret, render):
    fill_started = time.monotonic()
    with schema_context(schema):
        page_generation = _generations(cache, schema, [])[0]
    base = build_page()
    uuids = [str(item["uuid"]) for item in base["data"]]
    with schema_context(schema):
        generations = _generations(cache, schema, uuids)
    response = _assemble(base, lookup_details(uuids), strip_secret)
    rendered = render(response)
    SOURCES_CACHE_FILLED_SECONDS.labels("page").observe(time.monotonic() - fill_started)
    SOURCES_CACHE_READS.labels("page_fill").inc()
    with schema_context(schema):
        if (
            generations[0] == page_generation
            and get_generation(schema, "tenant") == tenant_generation
            and _generations(cache, schema, uuids) == generations
        ):
            cache.set(
                key,
                {
                    "tenant_generation": tenant_generation,
                    "generations": generations,
                    "response": response,
                    "rendered": rendered,
                },
                timeout=_ttl(),
            )
    return response, rendered


def get_or_fill_response(request, build_page, lookup_details, strip_secret, render):
    """Return an assembled snapshot after one batched tenant-epoch check."""
    schema = request.tenant.schema_name
    key = _page_key(request, schema)
    tenant_key = f"sources:gen:{schema}:tenant"
    cache = caches[CacheEnum.api]
    lock = f"{key}:fill"
    acquired = False
    try:
        with schema_context(schema):
            cached = cache.get_many([key, tenant_key])
            snapshot = cached.get(key)
            tenant_generation = cached.get(tenant_key) or get_generation(schema, "tenant")
            if tenant_generation is None:
                raise RuntimeError("Unable to initialize sources tenant generation")
            if snapshot is not None and snapshot["tenant_generation"] == tenant_generation:
                SOURCES_CACHE_READS.labels("hot").inc()
                return _snapshot_result(snapshot)
            acquired = cache.add(lock, 1, timeout=5)
            if not acquired:
                waited = _wait_for_fill(
                    cache, key, accept=lambda value: value["tenant_generation"] == tenant_generation
                )
                if waited is not None:
                    SOURCES_CACHE_READS.labels("wait_hit").inc()
                    return _snapshot_result(waited)
            if snapshot is not None:
                refreshed = _refresh_snapshot(cache, key, schema, snapshot, tenant_generation, lookup_details, render)
                if refreshed is not None:
                    return refreshed
        return _build_snapshot(cache, key, schema, tenant_generation, build_page, lookup_details, strip_secret, render)
    except Exception:
        SOURCES_CACHE_READS.labels("error_fallback").inc()
        LOG.exception("Unable to use sources response cache")
        base = build_page()
        response = _assemble(base, lookup_details([str(item["uuid"]) for item in base["data"]]), strip_secret)
        return response, render(response)
    finally:
        if acquired:
            try:
                with schema_context(schema):
                    cache.delete(lock)
            except Exception:
                LOG.exception("Unable to release sources response fill lock")


def _detail_keys(cache, schema, uuids):
    scopes = {uuid: f"provider:{uuid}" for uuid in uuids}
    generation_keys = {uuid: f"sources:gen:{schema}:{scope}" for uuid, scope in scopes.items()}
    generations = cache.get_many(generation_keys.values())
    for uuid in uuids:
        key = generation_keys[uuid]
        if key not in generations:
            generation = get_generation(schema, scopes[uuid])
            if generation is None:
                raise RuntimeError("Unable to initialize provider detail generation")
            generations[key] = generation
    return {uuid: _detail_key(schema, uuid, generations[generation_keys[uuid]]) for uuid in uuids}


def get_or_fill_details(schema, tenant, provider_uuids):
    """Read provider details in batches and recompute only missing providers."""
    uuids = [str(value) for value in provider_uuids]
    if not uuids:
        return {}
    try:
        with schema_context(schema):
            cache = caches[CacheEnum.api]
            keys = _detail_keys(cache, schema, uuids)
            cached = cache.get_many(keys.values())
    except Exception:
        SOURCES_CACHE_READS.labels("detail_error").inc()
        LOG.exception("Unable to read sources provider cache")
        return bulk_source_details(uuids, tenant)

    result = {uuid: copy.deepcopy(cached[keys[uuid]]) for uuid in uuids if keys[uuid] in cached}
    missing = [uuid for uuid in uuids if uuid not in result]
    SOURCES_CACHE_READS.labels("detail_hit").inc(len(result))
    SOURCES_CACHE_READS.labels("detail_miss").inc(len(missing))
    if missing:
        fill_started = time.monotonic()
        fresh = bulk_source_details(missing, tenant)
        SOURCES_CACHE_FILLED_SECONDS.labels("details").observe(time.monotonic() - fill_started)
        for uuid in missing:
            result[uuid] = fresh.get(uuid) or unlinked_source_details()
        try:
            with schema_context(schema):
                cache.set_many({keys[uuid]: result[uuid] for uuid in missing}, timeout=_ttl())
        except Exception:
            LOG.exception("Unable to fill sources provider cache")
    return result
