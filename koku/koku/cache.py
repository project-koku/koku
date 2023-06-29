#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Cache functions."""
import logging

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.dummy import DummyCache
from django.core.cache.backends.locmem import LocMemCache
from django_redis.cache import RedisCache
from redis import Redis

from api.common import log_json
from api.provider.models import Provider


class KokuCacheError(Exception):
    """KokuCacheError Error."""

    pass


LOG = logging.getLogger(__name__)

AWS_CACHE_PREFIX = "aws-view"
AZURE_CACHE_PREFIX = "azure-view"
GCP_CACHE_PREFIX = "gcp-view"
OCI_CACHE_PREFIX = "oci-view"
OPENSHIFT_CACHE_PREFIX = "openshift-view"
OPENSHIFT_AWS_CACHE_PREFIX = "openshift-aws-view"
OPENSHIFT_AZURE_CACHE_PREFIX = "openshift-azure-view"
OPENSHIFT_GCP_CACHE_PREFIX = "openshift-gcp-view"
OPENSHIFT_ALL_CACHE_PREFIX = "openshift-all-view"
SOURCES_CACHE_PREFIX = "sources"


def invalidate_view_cache_for_tenant_and_cache_key(schema_name, cache_key_prefix=None):
    """Invalidate our view cache for a specific tenant and source type.

    If cache_key_prefix is None, all views will be invalidated.
    """
    cache = caches["default"]
    if isinstance(cache, RedisCache):  # pragma: no cover
        cache = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            **settings.REDIS_CONNECTION_POOL_KWARGS,
        )
        all_keys = cache.keys("*")
        all_keys = [key.decode("utf-8") for key in all_keys]
    elif isinstance(cache, LocMemCache):
        all_keys = cache._cache.keys()
        all_keys = list(all_keys)
        all_keys = [key.split(":") for key in all_keys]
        all_keys = [":".join(splits[-2:]) for splits in all_keys]
    elif isinstance(cache, DummyCache):
        LOG.info(log_json(msg="skipping cache invalidation because views caching is disabled", schema=schema_name))
        return
    else:
        msg = "Using an unsupported caching backend!"
        raise KokuCacheError(msg)

    if cache_key_prefix:
        keys_to_invalidate = [key for key in all_keys if (schema_name in key and cache_key_prefix in key)]
    else:
        # Invalidate all cached views for the tenant
        keys_to_invalidate = [key for key in all_keys if schema_name in key]

    for key in keys_to_invalidate:
        cache.delete(key)

    LOG.info(log_json(msg="invalidated request cache", schema=schema_name, cache_key_prefix=cache_key_prefix))


def invalidate_view_cache_for_tenant_and_source_type(schema_name, source_type):
    """ "Invalidate our view cache for a specific tenant and source type."""
    cache_key_prefixes = ()
    if source_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
        cache_key_prefixes = (AWS_CACHE_PREFIX, OPENSHIFT_AWS_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)
    elif source_type in (Provider.PROVIDER_OCP):
        cache_key_prefixes = (
            OPENSHIFT_CACHE_PREFIX,
            OPENSHIFT_AWS_CACHE_PREFIX,
            OPENSHIFT_AZURE_CACHE_PREFIX,
            OPENSHIFT_ALL_CACHE_PREFIX,
            OPENSHIFT_GCP_CACHE_PREFIX,
        )
    elif source_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
        cache_key_prefixes = (AZURE_CACHE_PREFIX, OPENSHIFT_AZURE_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)
    elif source_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
        cache_key_prefixes = (GCP_CACHE_PREFIX, OPENSHIFT_GCP_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)
    elif source_type in (Provider.PROVIDER_OCI, Provider.PROVIDER_OCI_LOCAL):
        cache_key_prefixes = (OCI_CACHE_PREFIX,)

    for cache_key_prefix in cache_key_prefixes:
        invalidate_view_cache_for_tenant_and_cache_key(schema_name, cache_key_prefix)


def invalidate_view_cache_for_tenant_and_source_types(schema_name, source_types):
    """ "Invalidate our view cache for a specific tenant and a list source types."""
    for source_type in source_types:
        if source_type in Provider.PROVIDER_LIST:
            invalidate_view_cache_for_tenant_and_source_type(schema_name, source_type)
        else:
            LOG.info(
                log_json(
                    msg="unable to invalidate cache, not a valid source type",
                    schema=schema_name,
                    source_type=source_type,
                )
            )


def invalidate_view_cache_for_tenant_and_all_source_types(schema_name):
    """ "Invalidate our view cache for a specific tenant and all (non local) source types."""
    non_local_providers = [provider for provider in Provider.PROVIDER_LIST if "-local" not in provider]

    for source_type in non_local_providers:
        invalidate_view_cache_for_tenant_and_source_type(schema_name, source_type)


def get_cached_matching_tags(schema_name, provider_type):
    """Return cached OCP on Cloud matched tags if exists."""
    cache = caches["default"]
    cache_key = f"OCP-on-{provider_type}:{schema_name}:matching-tags"
    return cache.get(cache_key)


def set_cached_matching_tags(schema_name, provider_type, matched_tags):
    """Return cached OCP on Cloud matched tags if exists."""
    cache = caches["default"]
    cache_key = f"OCP-on-{provider_type}:{schema_name}:matching-tags"
    cache.set(cache_key, matched_tags)


def get_cached_infra_map(schema_name, provider_type, provider_uuid):
    """Return cached OCP on Cloud infra-map if exists."""
    cache = caches["default"]
    cache_key = f"OCP-on-{provider_type}:{schema_name}:{provider_uuid}:infra-map"
    return cache.get(cache_key)


def set_cached_infra_map(schema_name, provider_type, provider_uuid, infra_map):
    """Return cached OCP on Cloud infra-map if exists."""
    cache = caches["default"]
    cache_key = f"OCP-on-{provider_type}:{schema_name}:{provider_uuid}:infra-map"
    cache.set(cache_key, infra_map)
