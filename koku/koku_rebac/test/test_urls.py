#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""URL configuration for integration tests.

Always includes koku_rebac URLs regardless of the AUTHORIZATION_BACKEND
setting so that @override_settings can toggle the backend at test runtime
without fighting Django's import-time URL resolution.
"""
from django.conf import settings
from django.conf.urls import include
from django.urls import path

API_PATH_PREFIX = settings.API_PATH_PREFIX
if API_PATH_PREFIX != "":
    if API_PATH_PREFIX.startswith("/"):
        API_PATH_PREFIX = API_PATH_PREFIX[1:]
    if not API_PATH_PREFIX.endswith("/"):
        API_PATH_PREFIX = API_PATH_PREFIX + "/"

urlpatterns = [
    path(f"{API_PATH_PREFIX}v1/", include("api.urls")),
    path(f"{API_PATH_PREFIX}v1/", include("cost_models.urls")),
    path(f"{API_PATH_PREFIX}v1/access-management/", include("koku_rebac.urls")),
]
