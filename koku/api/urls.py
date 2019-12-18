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
    AzureCostView,
    AzureInstanceTypeView,
    AzureStorageView,
    AzureTagView,
    CloudAccountViewSet,
    CostModelMetricsMapViewSet,
    DataExportRequestViewSet,
    OCPAWSCostView,
    OCPAWSInstanceTypeView,
    OCPAWSStorageView,
    OCPAWSTagView,
    OCPAllCostView,
    OCPAllInstanceTypeView,
    OCPAllStorageView,
    OCPAllTagView,
    OCPAzureCostView,
    OCPAzureInstanceTypeView,
    OCPAzureStorageView,
    OCPAzureTagView,
    OCPCostView,
    OCPCpuView,
    OCPMemoryView,
    OCPTagView,
    OCPVolumeView,
    ProviderViewSet,
    SourcesProxyViewSet,
    StatusView,
    UserPreferenceViewSet,
    authentication,
    billing_source,
    openapi,
)


ROUTER = DefaultRouter()
ROUTER.register(r'dataexportrequests', DataExportRequestViewSet, base_name='dataexportrequests')
ROUTER.register(r'metrics', CostModelMetricsMapViewSet, base_name='metrics')
ROUTER.register(r'providers', ProviderViewSet)
ROUTER.register(r'sources', SourcesProxyViewSet, base_name='sources-proxy')
ROUTER.register(r'preferences', UserPreferenceViewSet, base_name='preferences')
ROUTER.register(r'cloud-accounts', CloudAccountViewSet, base_name='cloud_accounts')
# pylint: disable=invalid-name
urlpatterns = [

    url(r'^status/$', StatusView.as_view(), name='server-status'),
    url(r'^openapi.json', openapi, name='openapi'),
    url(r'^tags/aws/$', AWSTagView.as_view(), name='aws-tags'),
    url(r'^tags/azure/$', AzureTagView.as_view(), name='azure-tags'),
    url(r'^tags/openshift/$', OCPTagView.as_view(), name='openshift-tags'),
    url(r'^tags/openshift/infrastructures/all/$', OCPAllTagView.as_view(),
        name='openshift-all-tags'),
    url(r'^tags/openshift/infrastructures/aws/$', OCPAWSTagView.as_view(),
        name='openshift-aws-tags'),
    url(r'^tags/openshift/infrastructures/azure/$', OCPAzureTagView.as_view(),
        name='openshift-azure-tags'),
    url(r'^reports/aws/costs/$', AWSCostView.as_view(), name='reports-aws-costs'),
    url(r'^reports/aws/instance-types/$', AWSInstanceTypeView.as_view(),
        name='reports-aws-instance-type'),
    url(r'^reports/aws/storage/$', AWSStorageView.as_view(),
        name='reports-aws-storage'),
    url(r'^reports/azure/costs/$', AzureCostView.as_view(), name='reports-azure-costs'),
    url(r'^reports/azure/instance-types/$', AzureInstanceTypeView.as_view(),
        name='reports-azure-instance-type'),
    url(r'^reports/azure/storage/$', AzureStorageView.as_view(),
        name='reports-azure-storage'),
    url(r'^reports/openshift/costs/$', OCPCostView.as_view(),
        name='reports-openshift-costs'),
    url(r'^reports/openshift/memory/$', OCPMemoryView.as_view(),
        name='reports-openshift-memory'),
    url(r'^reports/openshift/compute/$', OCPCpuView.as_view(),
        name='reports-openshift-cpu'),
    url(r'^reports/openshift/volumes/$', OCPVolumeView.as_view(),
        name='reports-openshift-volume'),
    url(r'^reports/openshift/infrastructures/all/costs/$', OCPAllCostView.as_view(),
        name='reports-openshift-all-costs'),
    url(r'^reports/openshift/infrastructures/all/storage/$', OCPAllStorageView.as_view(),
        name='reports-openshift-all-storage'),
    url(r'^reports/openshift/infrastructures/all/instance-types/$',
        OCPAllInstanceTypeView.as_view(),
        name='reports-openshift-all-instance-type'),
    url(r'^reports/openshift/infrastructures/aws/costs/$', OCPAWSCostView.as_view(),
        name='reports-openshift-aws-costs'),
    url(r'^reports/openshift/infrastructures/aws/storage/$', OCPAWSStorageView.as_view(),
        name='reports-openshift-aws-storage'),
    url(r'^reports/openshift/infrastructures/aws/instance-types/$',
        OCPAWSInstanceTypeView.as_view(),
        name='reports-openshift-aws-instance-type'),
    url(r'^reports/openshift/infrastructures/azure/costs/$', OCPAzureCostView.as_view(),
        name='reports-openshift-azure-costs'),
    url(r'^reports/openshift/infrastructures/azure/storage/$', OCPAzureStorageView.as_view(),
        name='reports-openshift-azure-storage'),
    url(r'^reports/openshift/infrastructures/azure/instance-types/$',
        OCPAzureInstanceTypeView.as_view(),
        name='reports-openshift-azure-instance-type'),
    url(r'^sources/authentication/$', authentication, name='authentication'),
    url(r'^sources/billing_source/$', billing_source, name='billing-source'),
    url(r'^', include(ROUTER.urls)),
]
