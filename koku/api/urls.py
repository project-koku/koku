#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.conf import settings
from django.urls import path
from django.views.decorators.cache import cache_page
from rest_framework.routers import DefaultRouter

from api.common.deprecate_view import SunsetView
from api.views import AccountSettings
from api.views import AWSAccountRegionView
from api.views import AWSAccountView
from api.views import AWSCategoryView
from api.views import AWSCostForecastView
from api.views import AWSCostView
from api.views import AWSEC2ComputeInstanceView
from api.views import AWSEC2ComputeOperatingSystemView
from api.views import AWSEC2ComputeView
from api.views import AWSInstanceTypeView
from api.views import AWSOrganizationalUnitView
from api.views import AWSOrgView
from api.views import AWSServiceView
from api.views import AWSStorageView
from api.views import AWSTagView
from api.views import AzureCostForecastView
from api.views import AzureCostView
from api.views import AzureInstanceTypeView
from api.views import AzureRegionView
from api.views import AzureServiceView
from api.views import AzureStorageView
from api.views import AzureSubscriptionGuidView
from api.views import AzureTagView
from api.views import cloud_accounts
from api.views import CostGroupsAddView
from api.views import CostGroupsRemoveView
from api.views import CostGroupsView
from api.views import CostModelResourceTypesView
from api.views import GCPAccountView
from api.views import GCPCostForecastView
from api.views import GCPCostView
from api.views import GCPInstanceTypeView
from api.views import GCPProjectsView
from api.views import GCPRegionView
from api.views import GCPServiceView
from api.views import GCPStorageView
from api.views import GCPTagView
from api.views import get_currency
from api.views import get_exchange_rates
from api.views import IngressReportsDetailView
from api.views import IngressReportsView
from api.views import metrics
from api.views import OCPAllCostForecastView
from api.views import OCPAllCostView
from api.views import OCPAllInstanceTypeView
from api.views import OCPAllStorageView
from api.views import OCPAllTagView
from api.views import OCPAWSCostForecastView
from api.views import OCPAWSCostView
from api.views import OCPAWSInstanceTypeView
from api.views import OCPAWSStorageView
from api.views import OCPAWSTagView
from api.views import OCPAzureCostForecastView
from api.views import OCPAzureCostView
from api.views import OCPAzureInstanceTypeView
from api.views import OCPAzureStorageView
from api.views import OCPAzureTagView
from api.views import OCPClustersView
from api.views import OCPCostForecastView
from api.views import OCPCostView
from api.views import OCPCpuView
from api.views import OCPGCPCostForecastView
from api.views import OCPGCPCostView
from api.views import OCPGCPInstanceTypeView
from api.views import OCPGCPStorageView
from api.views import OCPGCPTagView
from api.views import OCPMemoryView
from api.views import OCPNetworkView
from api.views import OCPNodesView
from api.views import OCPProjectsView
from api.views import OCPReportVirtualMachinesView
from api.views import OCPTagView
from api.views import OCPVirtualMachinesView
from api.views import OCPVolumeView
from api.views import openapi
from api.views import ResourceTypeView
from api.views import SettingsAWSCategoryKeyView
from api.views import SettingsDisableAWSCategoryKeyView
from api.views import SettingsDisableTagView
from api.views import SettingsEnableAWSCategoryKeyView
from api.views import SettingsEnableTagView
from api.views import SettingsTagMappingChildAddView
from api.views import SettingsTagMappingChildRemoveView
from api.views import SettingsTagMappingChildView
from api.views import SettingsTagMappingParentRemoveView
from api.views import SettingsTagMappingParentView
from api.views import SettingsTagMappingView
from api.views import SettingsTagView
from api.views import StatusView
from api.views import UserAccessView
from api.views import UserCostTypeSettings
from koku.cache import AWS_CACHE_PREFIX
from koku.cache import AZURE_CACHE_PREFIX
from koku.cache import CacheEnum
from koku.cache import GCP_CACHE_PREFIX
from koku.cache import OPENSHIFT_ALL_CACHE_PREFIX
from koku.cache import OPENSHIFT_AWS_CACHE_PREFIX
from koku.cache import OPENSHIFT_AZURE_CACHE_PREFIX
from koku.cache import OPENSHIFT_CACHE_PREFIX
from koku.cache import OPENSHIFT_GCP_CACHE_PREFIX
from sources.api.views import SourcesViewSet

ROUTER = DefaultRouter()
ROUTER.register(r"sources", SourcesViewSet, basename="sources")
urlpatterns = [
    path("cloud-accounts/", cloud_accounts, name="cloud-accounts"),
    path("currency/", get_currency, name="currency"),
    path("exchange-rates/", get_exchange_rates, name="exchange-rates"),
    path("cost-type/", UserCostTypeSettings.as_view(), name="cost-type"),
    path("account-settings/", AccountSettings.as_view(), name="account-settings"),
    path("account-settings/<str:setting>/", AccountSettings.as_view(), name="get-account-setting"),
    path("status/", StatusView.as_view(), name="server-status"),
    path("openapi.json", openapi, name="openapi"),
    path("metrics/", metrics, name="metrics"),
    path(
        "tags/aws/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSTagView.as_view()
        ),
        name="aws-tags",
    ),
    path(
        "tags/azure/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AZURE_CACHE_PREFIX)(
            AzureTagView.as_view()
        ),
        name="azure-tags",
    ),
    path(
        "tags/gcp/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=GCP_CACHE_PREFIX)(
            GCPTagView.as_view()
        ),
        name="gcp-tags",
    ),
    path(
        "tags/openshift/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPTagView.as_view()
        ),
        name="openshift-tags",
    ),
    path(
        "tags/openshift/infrastructures/all/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX
        )(OCPAllTagView.as_view()),
        name="openshift-all-tags",
    ),
    path(
        "tags/openshift/infrastructures/aws/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX
        )(OCPAWSTagView.as_view()),
        name="openshift-aws-tags",
    ),
    path(
        "tags/openshift/infrastructures/azure/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX
        )(OCPAzureTagView.as_view()),
        name="openshift-azure-tags",
    ),
    path(
        "tags/openshift/infrastructures/gcp/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_GCP_CACHE_PREFIX
        )(OCPGCPTagView.as_view()),
        name="openshift-gcp-tags",
    ),
    path(
        "tags/aws/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSTagView.as_view()
        ),
        name="aws-tags-key",
    ),
    path(
        "tags/azure/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AZURE_CACHE_PREFIX)(
            AzureTagView.as_view()
        ),
        name="azure-tags-key",
    ),
    path(
        "tags/openshift/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPTagView.as_view()
        ),
        name="openshift-tags-key",
    ),
    path(
        "tags/gcp/<key>/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=GCP_CACHE_PREFIX)(
            GCPTagView.as_view()
        ),
        name="gcp-tags-key",
    ),
    path(
        "tags/openshift/infrastructures/all/<key>/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX
        )(OCPAllTagView.as_view()),
        name="openshift-all-tags-key",
    ),
    path(
        "tags/openshift/infrastructures/aws/<key>/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX
        )(OCPAWSTagView.as_view()),
        name="openshift-aws-tags-key",
    ),
    path(
        "tags/openshift/infrastructures/azure/<key>/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX
        )(OCPAzureTagView.as_view()),
        name="openshift-azure-tags-key",
    ),
    path(
        "reports/aws/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSCostView.as_view()
        ),
        name="reports-aws-costs",
    ),
    path(
        "reports/aws/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSInstanceTypeView.as_view()
        ),
        name="reports-aws-instance-type",
    ),
    path(
        "reports/aws/resources/ec2-compute/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSEC2ComputeView.as_view()
        ),
        name="reports-aws-ec2-compute",
    ),
    path(
        "reports/aws/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSStorageView.as_view()
        ),
        name="reports-aws-storage",
    ),
    path(
        "reports/azure/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AZURE_CACHE_PREFIX)(
            AzureCostView.as_view()
        ),
        name="reports-azure-costs",
    ),
    path(
        "reports/azure/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AZURE_CACHE_PREFIX)(
            AzureInstanceTypeView.as_view()
        ),
        name="reports-azure-instance-type",
    ),
    path(
        "reports/azure/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AZURE_CACHE_PREFIX)(
            AzureStorageView.as_view()
        ),
        name="reports-azure-storage",
    ),
    path(
        "reports/openshift/resources/virtual-machines/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPReportVirtualMachinesView.as_view()
        ),
        name="reports-openshift-virtual-machines",
    ),
    path(
        "reports/openshift/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPCostView.as_view()
        ),
        name="reports-openshift-costs",
    ),
    path(
        "reports/openshift/memory/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPMemoryView.as_view()
        ),
        name="reports-openshift-memory",
    ),
    path(
        "reports/openshift/compute/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPCpuView.as_view()
        ),
        name="reports-openshift-cpu",
    ),
    path(
        "reports/openshift/volumes/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPVolumeView.as_view()
        ),
        name="reports-openshift-volume",
    ),
    path(
        "reports/openshift/network/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_CACHE_PREFIX)(
            OCPNetworkView.as_view()
        ),
        name="reports-openshift-network",
    ),
    path(
        "reports/openshift/infrastructures/all/costs/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX
        )(OCPAllCostView.as_view()),
        name="reports-openshift-all-costs",
    ),
    path(
        "reports/openshift/infrastructures/all/storage/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX
        )(OCPAllStorageView.as_view()),
        name="reports-openshift-all-storage",
    ),
    path(
        "reports/openshift/infrastructures/all/instance-types/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_ALL_CACHE_PREFIX
        )(OCPAllInstanceTypeView.as_view()),
        name="reports-openshift-all-instance-type",
    ),
    path(
        "reports/openshift/infrastructures/aws/costs/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX
        )(OCPAWSCostView.as_view()),
        name="reports-openshift-aws-costs",
    ),
    path(
        "reports/openshift/infrastructures/aws/storage/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX
        )(OCPAWSStorageView.as_view()),
        name="reports-openshift-aws-storage",
    ),
    path(
        "reports/openshift/infrastructures/aws/instance-types/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AWS_CACHE_PREFIX
        )(OCPAWSInstanceTypeView.as_view()),
        name="reports-openshift-aws-instance-type",
    ),
    path(
        "reports/openshift/infrastructures/azure/costs/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX
        )(OCPAzureCostView.as_view()),
        name="reports-openshift-azure-costs",
    ),
    path(
        "reports/openshift/infrastructures/azure/storage/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX
        )(OCPAzureStorageView.as_view()),
        name="reports-openshift-azure-storage",
    ),
    path(
        "reports/openshift/infrastructures/azure/instance-types/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_AZURE_CACHE_PREFIX
        )(OCPAzureInstanceTypeView.as_view()),
        name="reports-openshift-azure-instance-type",
    ),
    path("ingress/reports/", IngressReportsView.as_view(), name="reports"),
    path("ingress/reports/<source>/", IngressReportsDetailView.as_view(), name="reports-detail"),
    path("settings/aws_category_keys/", SettingsAWSCategoryKeyView.as_view(), name="settings-aws-category-keys"),
    path("settings/cost-groups/", CostGroupsView.as_view(), name="settings-cost-groups"),
    path("settings/cost-groups/add/", CostGroupsAddView.as_view(), name="settings-cost-groups-add"),
    path("settings/cost-groups/remove/", CostGroupsRemoveView.as_view(), name="settings-cost-groups-remove"),
    path(
        "settings/aws_category_keys/enable/",
        SettingsEnableAWSCategoryKeyView.as_view(),
        name="settings-aws-category-keys-enable",
    ),
    path(
        "settings/aws_category_keys/disable/",
        SettingsDisableAWSCategoryKeyView.as_view(),
        name="settings-aws-category-keys-disable",
    ),
    path("settings/tags/", SettingsTagView.as_view(), name="settings-tags"),
    path("settings/tags/enable/", SettingsEnableTagView.as_view(), name="tags-enable"),
    path("settings/tags/disable/", SettingsDisableTagView.as_view(), name="tags-disable"),
    path("settings/tags/mappings/", SettingsTagMappingView.as_view(), name="tags-mapping"),
    path("settings/tags/mappings/child/", SettingsTagMappingChildView.as_view(), name="tags-mapping-child"),
    path("settings/tags/mappings/parent/", SettingsTagMappingParentView.as_view(), name="tags-mapping-parent"),
    path("settings/tags/mappings/child/add/", SettingsTagMappingChildAddView.as_view(), name="tags-mapping-child-add"),
    path(
        "settings/tags/mappings/child/remove/",
        SettingsTagMappingChildRemoveView.as_view(),
        name="tags-mapping-child-remove",
    ),
    path(
        "settings/tags/mappings/parent/remove/",
        SettingsTagMappingParentRemoveView.as_view(),
        name="tags-mapping-parent-remove",
    ),
    path("organizations/aws/", AWSOrgView.as_view(), name="aws-org-unit"),
    path("resource-types/", ResourceTypeView.as_view(), name="resource-types"),
    path("user-access/", UserAccessView.as_view(), name="user-access"),
    path("resource-types/aws-accounts/", AWSAccountView.as_view(), name="aws-accounts"),
    path(
        "resource-types/aws-ec2-compute-instances/",
        AWSEC2ComputeInstanceView.as_view(),
        name="aws-ec2-compute-instances",
    ),
    path(
        "resource-types/aws-ec2-compute-os/",
        AWSEC2ComputeOperatingSystemView.as_view(),
        name="aws-ec2-compute-os",
    ),
    path(
        "resource-types/aws-categories/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=AWS_CACHE_PREFIX)(
            AWSCategoryView.as_view()
        ),
        name="aws-categories",
    ),
    path("resource-types/gcp-accounts/", GCPAccountView.as_view(), name="gcp-accounts"),
    path("resource-types/gcp-projects/", GCPProjectsView.as_view(), name="gcp-projects"),
    # TODO gcp-gcp-projects should be removed after UI is pushed to prod.
    path("resource-types/gcp-gcp-projects/", GCPProjectsView.as_view(), name="gcp-gcp-projects"),
    path("resource-types/gcp-regions/", GCPRegionView.as_view(), name="gcp-regions"),
    path("resource-types/gcp-services/", GCPServiceView.as_view(), name="gcp-services"),
    path(
        "resource-types/aws-organizational-units/",
        AWSOrganizationalUnitView.as_view(),
        name="aws-organizational-units",
    ),
    path("resource-types/azure-regions/", AzureRegionView.as_view(), name="azure-regions"),
    path("resource-types/azure-services/", AzureServiceView.as_view(), name="azure-services"),
    path("resource-types/aws-services/", AWSServiceView.as_view(), name="aws-services"),
    path("resource-types/aws-regions/", AWSAccountRegionView.as_view(), name="aws-regions"),
    path(
        "resource-types/azure-subscription-guids/",
        AzureSubscriptionGuidView.as_view(),
        name="azure-subscription-guids",
    ),
    path("resource-types/openshift-clusters/", OCPClustersView.as_view(), name="openshift-clusters"),
    path("resource-types/openshift-projects/", OCPProjectsView.as_view(), name="openshift-projects"),
    path(
        "resource-types/openshift-virtual-machines/",
        OCPVirtualMachinesView.as_view(),
        name="openshift-virtual-machines",
    ),
    path("resource-types/openshift-nodes/", OCPNodesView.as_view(), name="openshift-nodes"),
    path("resource-types/cost-models/", CostModelResourceTypesView.as_view(), name="cost-models"),
    path("forecasts/aws/costs/", AWSCostForecastView.as_view(), name="aws-cost-forecasts"),
    path("forecasts/gcp/costs/", GCPCostForecastView.as_view(), name="gcp-cost-forecasts"),
    path("forecasts/azure/costs/", AzureCostForecastView.as_view(), name="azure-cost-forecasts"),
    path("forecasts/openshift/costs/", OCPCostForecastView.as_view(), name="openshift-cost-forecasts"),
    path(
        "forecasts/openshift/infrastructures/aws/costs/",
        OCPAWSCostForecastView.as_view(),
        name="openshift-aws-cost-forecasts",
    ),
    path(
        "forecasts/openshift/infrastructures/azure/costs/",
        OCPAzureCostForecastView.as_view(),
        name="openshift-azure-cost-forecasts",
    ),
    path(
        "forecasts/openshift/infrastructures/gcp/costs/",
        OCPGCPCostForecastView.as_view(),
        name="openshift-gcp-cost-forecasts",
    ),
    path(
        "forecasts/openshift/infrastructures/all/costs/",
        OCPAllCostForecastView.as_view(),
        name="openshift-all-cost-forecasts",
    ),
    path(
        "reports/gcp/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=GCP_CACHE_PREFIX)(
            GCPCostView.as_view()
        ),
        name="reports-gcp-costs",
    ),
    path(
        "reports/gcp/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=GCP_CACHE_PREFIX)(
            GCPInstanceTypeView.as_view()
        ),
        name="reports-gcp-instance-type",
    ),
    path(
        "reports/gcp/storage/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=GCP_CACHE_PREFIX)(
            GCPStorageView.as_view()
        ),
        name="reports-gcp-storage",
    ),
    path(
        "reports/openshift/infrastructures/gcp/costs/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_GCP_CACHE_PREFIX
        )(OCPGCPCostView.as_view()),
        name="reports-openshift-gcp-costs",
    ),
    path(
        "reports/openshift/infrastructures/gcp/instance-types/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_GCP_CACHE_PREFIX
        )(OCPGCPInstanceTypeView.as_view()),
        name="reports-openshift-gcp-instance-type",
    ),
    path(
        "reports/openshift/infrastructures/gcp/storage/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS, cache=CacheEnum.api, key_prefix=OPENSHIFT_GCP_CACHE_PREFIX
        )(OCPGCPStorageView.as_view()),
        name="reports-openshift-gcp-storage",
    ),
    # Sunset paths
    # These endpoints have been removed from the codebase
    path("settings/", SunsetView, name="settings"),
]
urlpatterns += ROUTER.urls
