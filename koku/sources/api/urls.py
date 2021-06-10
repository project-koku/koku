#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.conf.urls import include
from django.urls import path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from sources.api.status import get_status
from sources.api.views import source_status
from sources.api.views import SourcesViewSet

ROUTER = DefaultRouter()
ROUTER.register(r"sources", SourcesViewSet)

urlpatterns = [
    path("status/", get_status, name="server-status"),
    path("source-status/", source_status, name="source-status"),
    path("source-status", RedirectView.as_view(pattern_name="source-status"), name="source-status-redirect"),
    path("", include(ROUTER.urls)),
]
