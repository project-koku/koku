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
from rest_framework.routers import DefaultRouter

from api.views import (
    AWSCostView,
    AWSInstanceTypeView,
    AWSStorageView,
    AWSTagView,
    CostModelMetricsMapViewSet,
    OCPAWSCostView,
    OCPAWSInstanceTypeView,
    OCPAWSStorageView,
    OCPAWSTagView,
    OCPCostView,
    OCPCpuView,
    OCPMemoryView,
    OCPTagView,
    OCPVolumeView,
    ProviderViewSet,
    StatusView,
    UserPreferenceViewSet,
)

ROUTER = DefaultRouter()
ROUTER.register(r'metrics', CostModelMetricsMapViewSet, base_name='metrics')
ROUTER.register(r'providers', ProviderViewSet)
ROUTER.register(r'preferences', UserPreferenceViewSet, base_name='preferences')

# pylint: disable=invalid-name
urlpatterns = [
    url(r'^status/$', StatusView.as_view(), name='server-status'),
    url(r'^tags/aws/$', AWSTagView.as_view(), name='aws-tags'),
    url(r'^tags/openshift/$', OCPTagView.as_view(), name='openshift-tags'),
    url(r'^tags/openshift/infrastructures/aws/$', OCPAWSTagView.as_view(),
        name='openshift-aws-tags'),
    url(r'^reports/aws/costs/$', AWSCostView.as_view(), name='reports-aws-costs'),
    url(r'^reports/aws/instance-types/$', AWSInstanceTypeView.as_view(),
        name='reports-aws-instance-type'),
    url(r'^reports/aws/storage/$', AWSStorageView.as_view(),
        name='reports-aws-storage'),
    url(r'^reports/openshift/costs/$', OCPCostView.as_view(),
        name='reports-openshift-costs'),
    url(r'^reports/openshift/memory/$', OCPMemoryView.as_view(),
        name='reports-openshift-memory'),
    url(r'^reports/openshift/compute/$', OCPCpuView.as_view(),
        name='reports-openshift-cpu'),
    url(r'^reports/openshift/volumes/$', OCPVolumeView.as_view(),
        name='reports-openshift-volume'),
    url(r'^reports/openshift/infrastructures/aws/costs/$', OCPAWSCostView.as_view(),
        name='reports-openshift-aws-costs'),
    url(r'^reports/openshift/infrastructures/aws/storage/$', OCPAWSStorageView.as_view(),
        name='reports-openshift-aws-storage'),
    url(r'^reports/openshift/infrastructures/aws/instance-types/$',
        OCPAWSInstanceTypeView.as_view(),
        name='reports-openshift-aws-instance-type'),
    url(r'^', include(ROUTER.urls)),
]
