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
from django.conf import settings
from django.urls import path
from django.views.decorators.cache import cache_page
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
from koku.cache import AWS_CACHE_PREFIX
from koku.cache import AZURE_CACHE_PREFIX
from koku.cache import OPENSHIFT_ALL_CACHE_PREFIX
from koku.cache import OPENSHIFT_AWS_CACHE_PREFIX
from koku.cache import OPENSHIFT_AZURE_CACHE_PREFIX
from koku.cache import OPENSHIFT_CACHE_PREFIX
from sources.api.views import SourcesViewSet


ROUTER = DefaultRouter()
ROUTER.register(r"dataexportrequests", DataExportRequestViewSet, basename="dataexportrequests")
ROUTER.register(r"sources", SourcesViewSet, basename="sources")
urlpatterns = [
    path("cloud-accounts/", cloud_accounts, name="cloud-accounts"),
    path("status/", StatusView.as_view(), name="server-status"),
    path("openapi.json", openapi, name="openapi"),
    path("metrics/", metrics, name="metrics"),
    path(
        "tags/aws/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSTagView.as_view()),
        name="aws-tags",
    ),
    path(
        "tags/azure/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(AzureTagView.as_view()),
        name="azure-tags",
    ),
    path(
        "tags/openshift/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(OCPTagView.as_view()),
        name="openshift-tags",
    ),
    path(
        "tags/openshift/infrastructures/all/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllTagView.as_view()
        ),
        name="openshift-all-tags",
    ),
    path(
        "tags/openshift/infrastructures/aws/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSTagView.as_view()
        ),
        name="openshift-aws-tags",
    ),
    path(
        "tags/openshift/infrastructures/azure/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureTagView.as_view()
        ),
        name="openshift-azure-tags",
    ),
    path(
        "tags/aws/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSTagView.as_view()),
        name="aws-tags-key",
    ),
    path(
        "tags/azure/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(AzureTagView.as_view()),
        name="azure-tags-key",
    ),
    path(
        "tags/openshift/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(OCPTagView.as_view()),
        name="openshift-tags-key",
    ),
    path(
        "tags/openshift/infrastructures/all/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllTagView.as_view()
        ),
        name="openshift-all-tags-key",
    ),
    path(
        "tags/openshift/infrastructures/aws/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSTagView.as_view()
        ),
        name="openshift-aws-tags-key",
    ),
    path(
        "tags/openshift/infrastructures/azure/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureTagView.as_view()
        ),
        name="openshift-azure-tags-key",
    ),
    path(
        "reports/aws/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSCostView.as_view()),
        name="reports-aws-costs",
    ),
    path(
        "reports/aws/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(
            AWSInstanceTypeView.as_view()
        ),
        name="reports-aws-instance-type",
    ),
    path(
        "reports/aws/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSStorageView.as_view()),
        name="reports-aws-storage",
    ),
    path(
        "reports/azure/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(AzureCostView.as_view()),
        name="reports-azure-costs",
    ),
    path(
        "reports/azure/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(
            AzureInstanceTypeView.as_view()
        ),
        name="reports-azure-instance-type",
    ),
    path(
        "reports/azure/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(
            AzureStorageView.as_view()
        ),
        name="reports-azure-storage",
    ),
    path(
        "reports/openshift/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPCostView.as_view()
        ),
        name="reports-openshift-costs",
    ),
    path(
        "reports/openshift/memory/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPMemoryView.as_view()
        ),
        name="reports-openshift-memory",
    ),
    path(
        "reports/openshift/compute/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(OCPCpuView.as_view()),
        name="reports-openshift-cpu",
    ),
    path(
        "reports/openshift/volumes/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPVolumeView.as_view()
        ),
        name="reports-openshift-volume",
    ),
    path(
        "reports/openshift/infrastructures/all/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllCostView.as_view()
        ),
        name="reports-openshift-all-costs",
    ),
    path(
        "reports/openshift/infrastructures/all/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllStorageView.as_view()
        ),
        name="reports-openshift-all-storage",
    ),
    path(
        "reports/openshift/infrastructures/all/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllInstanceTypeView.as_view()
        ),
        name="reports-openshift-all-instance-type",
    ),
    path(
        "reports/openshift/infrastructures/aws/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSCostView.as_view()
        ),
        name="reports-openshift-aws-costs",
    ),
    path(
        "reports/openshift/infrastructures/aws/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSStorageView.as_view()
        ),
        name="reports-openshift-aws-storage",
    ),
    path(
        "reports/openshift/infrastructures/aws/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSInstanceTypeView.as_view()
        ),
        name="reports-openshift-aws-instance-type",
    ),
    path(
        "reports/openshift/infrastructures/azure/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureCostView.as_view()
        ),
        name="reports-openshift-azure-costs",
    ),
    path(
        "reports/openshift/infrastructures/azure/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureStorageView.as_view()
        ),
        name="reports-openshift-azure-storage",
    ),
    path(
        "reports/openshift/infrastructures/azure/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureInstanceTypeView.as_view()
        ),
        name="reports-openshift-azure-instance-type",
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings", RedirectView.as_view(pattern_name="settings"), name="settings-redirect"),
    path("organizations/aws/", AWSOrgView.as_view(), name="aws-org-unit"),
]
urlpatterns += ROUTER.urls
