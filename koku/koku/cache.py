#
# Copyright 2020 Red Hat, Inc.
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
"""Cache functions."""
import logging

from django.core.cache import caches

from api.provider.models import Provider


LOG = logging.getLogger(__name__)

AWS_CACHE_PREFIX = "aws-view"
AZURE_CACHE_PREFIX = "azure-view"
OPENSHIFT_CACHE_PREFIX = "openshift-view"
OPENSHIFT_AWS_CACHE_PREFIX = "openshift-aws-view"
OPENSHIFT_AZURE_CACHE_PREFIX = "openshift-azure-view"
OPENSHIFT_ALL_CACHE_PREFIX = "openshift-all-view"


def invalidate_view_cache_for_tenant_and_cache_key(schema_name, cache_key_prefix=None):
    """Invalidate our view cache for a specific tenant and source type.

    If cache_key_prefix is None, all views will be invalidated.
    """
    cache = caches["default"]

    all_keys = cache.keys("*")
    if cache_key_prefix:
        keys_to_invalidate = [key for key in all_keys if (schema_name in key and cache_key_prefix in key)]
    else:
        # Invalidate all cached views for the tenant
        keys_to_invalidate = [key for key in all_keys if schema_name in key]

    cache.delete_many(keys_to_invalidate)
    msg = f"Invalidated request cache for\n\ttenant: {schema_name}\n\tview: {cache_key_prefix}"
    LOG.info(msg)


def invalidate_view_cache_for_tenant_and_source_type(schema_name, source_type):
    """"Invalidate our view cache for a specific tenant and source type."""
    cache_key_prefixes = ()
    if source_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
        cache_key_prefixes = (AWS_CACHE_PREFIX, OPENSHIFT_AWS_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)
    elif source_type in (Provider.PROVIDER_OCP):
        cache_key_prefixes = (
            OPENSHIFT_CACHE_PREFIX,
            OPENSHIFT_AWS_CACHE_PREFIX,
            OPENSHIFT_AZURE_CACHE_PREFIX,
            OPENSHIFT_ALL_CACHE_PREFIX,
        )
    elif source_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
        cache_key_prefixes = (AZURE_CACHE_PREFIX, OPENSHIFT_AZURE_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)

    for cache_key_prefix in cache_key_prefixes:
        invalidate_view_cache_for_tenant_and_cache_key(schema_name, cache_key_prefix)
