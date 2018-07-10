# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Describes the urls and patterns for the API application."""
from django.conf.urls import include, url
from rest_framework.authtoken import views
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter

from api.views import (CustomerViewSet,
                       ProviderViewSet,
                       UserPreferenceViewSet,
                       UserViewSet,
                       costs,
                       instance_type,
                       status,
                       storage)

ROUTER = DefaultRouter()
ROUTER.register(r'customers', CustomerViewSet)
ROUTER.register(r'providers', ProviderViewSet)
ROUTER.register(r'users', UserViewSet)

USER_ROUTER = NestedSimpleRouter(ROUTER, r'users', lookup='user')
USER_ROUTER.register(r'preferences', UserPreferenceViewSet,
                     base_name='preferences')

# pylint: disable=invalid-name
urlpatterns = [
    url(r'^token-auth/', views.obtain_auth_token, name='token-auth'),
    url(r'^status/$', status, name='server-status'),
    url(r'^reports/costs/$', costs, name='reports-costs'),
    url(r'^reports/inventory/instance-type/$', instance_type, name='reports-instance-type'),
    url(r'^reports/inventory/storage/$', storage, name='reports-storage'),
    url(r'^', include(ROUTER.urls)),
    url(r'^', include(USER_ROUTER.urls))
]
