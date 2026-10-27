"""Generation keys used to refresh only affected sources cache entries."""
import logging
from uuid import uuid4

from django.core.cache import caches
from django.db import transaction
from django_tenants.utils import schema_context
from prometheus_client import Counter

from koku.settings import CacheEnum

LOG = logging.getLogger(__name__)
SOURCES_CACHE_GENERATIONS = Counter(
    "sources_list_cache_generations_total", "Sources list generation changes", ["scope"]
)


def _generation_key(schema, scope):
    return f"sources:gen:{schema}:{scope}"


def get_generation(schema, scope):
    """Return a stable generation, or None when the cache cannot be used."""
    key = _generation_key(schema, scope)
    try:
        with schema_context(schema):
            cache = caches[CacheEnum.api]
            generation = cache.get(key)
            if generation is None:
                cache.add(key, str(uuid4()), timeout=None)
                generation = cache.get(key)
            return generation
    except Exception:
        LOG.exception("Unable to read sources cache generation")
        return None


def _advance(schema, scopes):
    values = {_generation_key(schema, scope): str(uuid4()) for scope in scopes}
    values[_generation_key(schema, "tenant")] = str(uuid4())
    try:
        with schema_context(schema):
            cache = caches[CacheEnum.api]
            cache.set_many(values, timeout=None)
        SOURCES_CACHE_GENERATIONS.labels("page").inc("page" in scopes)
        SOURCES_CACHE_GENERATIONS.labels("provider").inc(sum(scope != "page" for scope in scopes))
    except Exception:
        LOG.exception("Unable to advance sources cache generation")


def advance_provider(schema, provider_uuid):
    """Advance one provider's dynamic detail generation without key scans."""
    _advance(schema, [f"provider:{provider_uuid}"])


def _provider_scopes(provider_uuid, include_dependents):
    """Scope the provider and, optionally, OCP providers using it as infrastructure."""
    uuids = {str(provider_uuid)}
    if include_dependents:
        from api.provider.models import Provider

        dependents = Provider.objects.filter(infrastructure__infrastructure_provider_id=provider_uuid)
        uuids.update(str(uuid) for uuid in dependents.values_list("uuid", flat=True))
    return [f"provider:{uuid}" for uuid in uuids]


def dynamic_source_changed_on_commit(schema, provider_uuid, *, include_dependents=False):
    """Only flagged tenants pay for manifest and cost-model generation changes."""

    def refresh():
        from masu.processor import is_feature_flag_enabled_by_schema
        from masu.processor import SOURCES_LIST_GRANULAR_CACHE_FLAG

        if not is_feature_flag_enabled_by_schema(schema, SOURCES_LIST_GRANULAR_CACHE_FLAG, dev_fallback=True):
            return
        _advance(schema, _provider_scopes(provider_uuid, include_dependents))

    transaction.on_commit(refresh)


def source_cache_changed(schema, *, page=False, provider_uuid=None, include_dependents=False):
    """Use targeted generations on the new path and retain legacy invalidation elsewhere."""
    from koku.cache import invalidate_cache_for_tenant_and_cache_key
    from koku.cache import SOURCES_CACHE_PREFIX
    from masu.processor import is_feature_flag_enabled_by_schema
    from masu.processor import SOURCES_LIST_GRANULAR_CACHE_FLAG

    if not is_feature_flag_enabled_by_schema(schema, SOURCES_LIST_GRANULAR_CACHE_FLAG, dev_fallback=True):
        invalidate_cache_for_tenant_and_cache_key(schema, SOURCES_CACHE_PREFIX)
        return

    def refresh():
        scopes = ["page"] if page else []
        if provider_uuid is not None:
            scopes.extend(_provider_scopes(provider_uuid, include_dependents))
        _advance(schema, scopes)

    transaction.on_commit(refresh)
