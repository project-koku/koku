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
from django.urls import path
from django.views.generic.base import RedirectView
from rest_framework.routers import DefaultRouter

from api.views import AWSCostView
from api.views import AWSInstanceTypeView
from api.views import AWSOrgView
from api.views import AWSStorageView
from api.views import AWSTagView
from api.views import AzureCostView
from api.views import AzureInstanceTypeView
from api.views import AzureStorageView
from api.views import AzureTagView
from api.views import cloud_accounts
from api.views import DataExportRequestViewSet
from api.views import metrics
from api.views import OCPAllCostView
from api.views import OCPAllInstanceTypeView
from api.views import OCPAllStorageView
from api.views import OCPAllTagView
from api.views import OCPAWSCostView
from api.views import OCPAWSInstanceTypeView
from api.views import OCPAWSStorageView
from api.views import OCPAWSTagView
from api.views import OCPAzureCostView
from api.views import OCPAzureInstanceTypeView
from api.views import OCPAzureStorageView
from api.views import OCPAzureTagView
from api.views import OCPCostView
from api.views import OCPCpuView
from api.views import OCPMemoryView
from api.views import OCPTagView
from api.views import OCPVolumeView
from api.views import openapi
from api.views import SettingsView
from api.views import StatusView
from sources.api.views import SourcesViewSet


ROUTER = DefaultRouter()
ROUTER.register(r"dataexportrequests", DataExportRequestViewSet, basename="dataexportrequests")
ROUTER.register(r"sources", SourcesViewSet, basename="sources")
# pylint: disable=invalid-name
urlpatterns = [
    path("cloud-accounts/", cloud_accounts, name="cloud-accounts"),
    path("status/", StatusView.as_view(), name="server-status"),
    path("openapi.json", openapi, name="openapi"),
    path("metrics/", metrics, name="metrics"),
    path("tags/aws/", AWSTagView.as_view(), name="aws-tags"),
    path("tags/azure/", AzureTagView.as_view(), name="azure-tags"),
    path("tags/openshift/", OCPTagView.as_view(), name="openshift-tags"),
    path("tags/openshift/infrastructures/all/", OCPAllTagView.as_view(), name="openshift-all-tags"),
    path("tags/openshift/infrastructures/aws/", OCPAWSTagView.as_view(), name="openshift-aws-tags"),
    path("tags/openshift/infrastructures/azure/", OCPAzureTagView.as_view(), name="openshift-azure-tags"),
    path("tags/aws/<key>/", AWSTagView.as_view(), name="aws-tags-key"),
    path("tags/azure/<key>/", AzureTagView.as_view(), name="azure-tags-key"),
    path("tags/openshift/<key>/", OCPTagView.as_view(), name="openshift-tags-key"),
    path("tags/openshift/infrastructures/all/<key>/", OCPAllTagView.as_view(), name="openshift-all-tags-key"),
    path("tags/openshift/infrastructures/aws/<key>/", OCPAWSTagView.as_view(), name="openshift-aws-tags-key"),
    path("tags/openshift/infrastructures/azure/<key>/", OCPAzureTagView.as_view(), name="openshift-azure-tags-key"),
    path("reports/aws/costs/", AWSCostView.as_view(), name="reports-aws-costs"),
    path("reports/aws/instance-types/", AWSInstanceTypeView.as_view(), name="reports-aws-instance-type"),
    path("reports/aws/storage/", AWSStorageView.as_view(), name="reports-aws-storage"),
    path("reports/azure/costs/", AzureCostView.as_view(), name="reports-azure-costs"),
    path("reports/azure/instance-types/", AzureInstanceTypeView.as_view(), name="reports-azure-instance-type"),
    path("reports/azure/storage/", AzureStorageView.as_view(), name="reports-azure-storage"),
    path("reports/openshift/costs/", OCPCostView.as_view(), name="reports-openshift-costs"),
    path("reports/openshift/memory/", OCPMemoryView.as_view(), name="reports-openshift-memory"),
    path("reports/openshift/compute/", OCPCpuView.as_view(), name="reports-openshift-cpu"),
    path("reports/openshift/volumes/", OCPVolumeView.as_view(), name="reports-openshift-volume"),
    path("reports/openshift/infrastructures/all/costs/", OCPAllCostView.as_view(), name="reports-openshift-all-costs"),
    path(
        "reports/openshift/infrastructures/all/storage/",
        OCPAllStorageView.as_view(),
        name="reports-openshift-all-storage",
    ),
    path(
        "reports/openshift/infrastructures/all/instance-types/",
        OCPAllInstanceTypeView.as_view(),
        name="reports-openshift-all-instance-type",
    ),
    path("reports/openshift/infrastructures/aws/costs/", OCPAWSCostView.as_view(), name="reports-openshift-aws-costs"),
    path(
        "reports/openshift/infrastructures/aws/storage/",
        OCPAWSStorageView.as_view(),
        name="reports-openshift-aws-storage",
    ),
    path(
        "reports/openshift/infrastructures/aws/instance-types/",
        OCPAWSInstanceTypeView.as_view(),
        name="reports-openshift-aws-instance-type",
    ),
    path(
        "reports/openshift/infrastructures/azure/costs/",
        OCPAzureCostView.as_view(),
        name="reports-openshift-azure-costs",
    ),
    path(
        "reports/openshift/infrastructures/azure/storage/",
        OCPAzureStorageView.as_view(),
        name="reports-openshift-azure-storage",
    ),
    path(
        "reports/openshift/infrastructures/azure/instance-types/",
        OCPAzureInstanceTypeView.as_view(),
        name="reports-openshift-azure-instance-type",
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings", RedirectView.as_view(pattern_name="settings"), name="settings-redirect"),
    path("organizations/aws/", AWSOrgView.as_view(), name="aws-org-unit"),
]
urlpatterns += ROUTER.urls
