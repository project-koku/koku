#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Endpoint for cache invalidation."""
import logging
from typing import Literal

from pydantic import BaseModel
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings

from koku.cache import CacheEnum
from koku.cache import invalidate_cache_for_tenant_and_cache_key

LOG = logging.getLogger("__name__")


class CacheInvalidationEvent(BaseModel):
    schema_name: str
    cache_name: Literal[CacheEnum.default, CacheEnum.rbac]  # we don't support invalidating the CacheEnum.worker cache


class CacheInvalidationEvents(BaseModel):
    events: list[CacheInvalidationEvent]


@api_view(http_method_names=["POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def invalidate_cache(request: Request):
    data = request.data
    if isinstance(data, dict):
        data = [data]
    try:
        events = CacheInvalidationEvents(events=data)
    except ValidationError as e:
        LOG.warning(f"validation error: {str(e)}")
        return Response(e.errors(), status=status.HTTP_400_BAD_REQUEST)

    for event in events.events:
        if event.cache_name == CacheEnum.default:
            invalidate_cache_for_tenant_and_cache_key(event.schema_name, cache_name=CacheEnum.default)
        elif event.cache_name == CacheEnum.rbac:
            invalidate_cache_for_tenant_and_cache_key(event.schema_name, cache_name=CacheEnum.rbac)

    return Response({"msg": "invalidated cache"} | events.model_dump(), status=status.HTTP_200_OK)
