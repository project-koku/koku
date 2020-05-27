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

AWS_TAGS_API_VIEW_NAME = "aws-tags"
AWS_TAGS_KEY_API_VIEW_NAME = "aws-tags-key"
AWS_COST_API_VIEW_NAME = "reports-aws-costs"
AWS_INSTANCE_TYPE_API_VIEW_NAME = "reports-aws-instance-type"
AWS_STORAGE_API_VIEW_NAME = "reports-aws-storage"

AZURE_TAGS_API_VIEW_NAME = "azure-tags"
AZURE_TAGS_KEY_API_VIEW_NAME = "azure-tags-key"
AZURE_COST_API_VIEW_NAME = "reports-azure-costs"
AZURE_INSTANCE_TYPE_API_VIEW_NAME = "reports-azure-instance-type"
AZURE_STORAGE_API_VIEW_NAME = "reports-azure-storage"

OPENSHIFT_ALL_TAGS_API_VIEW_NAME = "openshift-all-tags"
OPENSHIFT_ALL_TAGS_KEY_API_VIEW_NAME = "openshift-all-tags-key"
OPENSHIFT_ALL_COST_API_VIEW_NAME = "reports-openshift-all-costs"
OPENSHIFT_ALL_INSTANCE_TYPE_API_VIEW_NAME = "reports-openshift-all-instance-type"
OPENSHIFT_ALL_STORAGE_API_VIEW_NAME = "reports-openshift-all-storage"

OPENSHIFT_AWS_TAGS_API_VIEW_NAME = "openshift-aws-tags"
OPENSHIFT_AWS_TAGS_KEY_API_VIEW_NAME = "openshift-aws-tags-key"
OPENSHIFT_AWS_COST_API_VIEW_NAME = "reports-openshift-aws-costs"
OPENSHIFT_AWS_INSTANCE_TYPE_API_VIEW_NAME = "reports-openshift-aws-instance-type"
OPENSHIFT_AWS_STORAGE_API_VIEW_NAME = "reports-openshift-aws-storage"

OPENSHIFT_AZURE_TAGS_API_VIEW_NAME = "openshift-azure-tags"
OPENSHIFT_AZURE_TAGS_KEY_API_VIEW_NAME = "openshift-azure-tags-key"
OPENSHIFT_AZURE_COST_API_VIEW_NAME = "reports-openshift-azure-costs"
OPENSHIFT_AZURE_INSTANCE_TYPE_API_VIEW_NAME = "reports-openshift-azure-instance-type"
OPENSHIFT_AZURE_STORAGE_API_VIEW_NAME = "reports-openshift-azure-storage"

OPENSHIFT_TAGS_API_VIEW_NAME = "openshift-tags"
OPENSHIFT_TAGS_KEY_API_VIEW_NAME = "openshift-tags-key"
OPENSHIFT_COST_API_VIEW_NAME = "reports-openshift-costs"
OPENSHIFT_MEMORY_API_VIEW_NAME = "reports-openshift-memory"
OPENSHIFT_CPU_API_VIEW_NAME = "reports-openshift-cpu"
OPENSHIFT_VOLUME_API_VIEW_NAME = "reports-openshift-volume"

AWS_CACHE_PREFIX = "aws-view"
AZURE_CACHE_PREFIX = "azure-view"
OPENSHIFT_CACHE_PREFIX = "openshift-view"
OPENSHIFT_AWS_CACHE_PREFIX = "openshift-aws-view"
OPENSHIFT_AZURE_CACHE_PREFIX = "openshift-azure-view"
OPENSHIFT_ALL_CACHE_PREFIX = "openshift-all-view"

ROUTER = DefaultRouter()
ROUTER.register(r"dataexportrequests", DataExportRequestViewSet, basename="dataexportrequests")
ROUTER.register(r"sources", SourcesViewSet, basename="sources")
# pylint: disable=invalid-name
urlpatterns = [
    path("cloud-accounts/", cloud_accounts, name="cloud-accounts"),
    path("status/", StatusView.as_view(), name="server-status"),
    path("openapi.json", openapi, name="openapi"),
    path("metrics/", metrics, name="metrics"),
    path(
        "tags/aws/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSTagView.as_view()),
        name=AWS_TAGS_API_VIEW_NAME,
    ),
    path(
        "tags/azure/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(AzureTagView.as_view()),
        name=AZURE_TAGS_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(OCPTagView.as_view()),
        name=OPENSHIFT_TAGS_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/infrastructures/all/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllTagView.as_view()
        ),
        name=OPENSHIFT_ALL_TAGS_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/infrastructures/aws/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSTagView.as_view()
        ),
        name=OPENSHIFT_AWS_TAGS_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/infrastructures/azure/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureTagView.as_view()
        ),
        name=OPENSHIFT_AZURE_TAGS_API_VIEW_NAME,
    ),
    path(
        "tags/aws/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSTagView.as_view()),
        name=AWS_TAGS_KEY_API_VIEW_NAME,
    ),
    path(
        "tags/azure/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(AzureTagView.as_view()),
        name=AZURE_TAGS_KEY_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(OCPTagView.as_view()),
        name=OPENSHIFT_TAGS_KEY_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/infrastructures/all/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllTagView.as_view()
        ),
        name=OPENSHIFT_ALL_TAGS_KEY_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/infrastructures/aws/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSTagView.as_view()
        ),
        name=OPENSHIFT_AWS_TAGS_KEY_API_VIEW_NAME,
    ),
    path(
        "tags/openshift/infrastructures/azure/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureTagView.as_view()
        ),
        name=OPENSHIFT_AZURE_TAGS_KEY_API_VIEW_NAME,
    ),
    path(
        "reports/aws/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSCostView.as_view()),
        name=AWS_COST_API_VIEW_NAME,
    ),
    path(
        "reports/aws/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(
            AWSInstanceTypeView.as_view()
        ),
        name=AWS_INSTANCE_TYPE_API_VIEW_NAME,
    ),
    path(
        "reports/aws/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AWS_CACHE_PREFIX)(AWSStorageView.as_view()),
        name=AWS_STORAGE_API_VIEW_NAME,
    ),
    path(
        "reports/azure/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(AzureCostView.as_view()),
        name=AZURE_COST_API_VIEW_NAME,
    ),
    path(
        "reports/azure/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(
            AzureInstanceTypeView.as_view()
        ),
        name=AZURE_INSTANCE_TYPE_API_VIEW_NAME,
    ),
    path(
        "reports/azure/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=AZURE_CACHE_PREFIX)(
            AzureStorageView.as_view()
        ),
        name=AZURE_STORAGE_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPCostView.as_view()
        ),
        name=OPENSHIFT_COST_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/memory/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPMemoryView.as_view()
        ),
        name=OPENSHIFT_MEMORY_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/compute/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(OCPCpuView.as_view()),
        name=OPENSHIFT_CPU_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/volumes/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPVolumeView.as_view()
        ),
        name=OPENSHIFT_VOLUME_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/all/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllCostView.as_view()
        ),
        name=OPENSHIFT_ALL_COST_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/all/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllStorageView.as_view()
        ),
        name=OPENSHIFT_ALL_STORAGE_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/all/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX)(
            OCPAllInstanceTypeView.as_view()
        ),
        name=OPENSHIFT_ALL_INSTANCE_TYPE_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/aws/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSCostView.as_view()
        ),
        name=OPENSHIFT_AWS_COST_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/aws/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSStorageView.as_view()
        ),
        name=OPENSHIFT_AWS_STORAGE_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/aws/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX)(
            OCPAWSInstanceTypeView.as_view()
        ),
        name=OPENSHIFT_AWS_INSTANCE_TYPE_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/azure/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureCostView.as_view()
        ),
        name=OPENSHIFT_AZURE_COST_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/azure/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureStorageView.as_view()
        ),
        name=OPENSHIFT_AZURE_STORAGE_API_VIEW_NAME,
    ),
    path(
        "reports/openshift/infrastructures/azure/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX)(
            OCPAzureInstanceTypeView.as_view()
        ),
        name=OPENSHIFT_AZURE_INSTANCE_TYPE_API_VIEW_NAME,
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings", RedirectView.as_view(pattern_name="settings"), name="settings-redirect"),
]
urlpatterns += ROUTER.urls
