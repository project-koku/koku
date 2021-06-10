#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.conf.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter

from cost_models.views import CostModelViewSet

ROUTER = DefaultRouter()
ROUTER.register(r"cost-models", CostModelViewSet, basename="cost-models")

urlpatterns = [path("", include(ROUTER.urls))]
