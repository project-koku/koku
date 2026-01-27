#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for cost entry tables."""
from django.conf import settings

from reporting.currency.models import CurrencySettings
from reporting.ingress.models import IngressReports
from reporting.partition.models import PartitionedTable
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.openshift.models import OCPAllComputeSummaryPT
from reporting.provider.all.openshift.models import OCPAllCostLineItemDailySummaryP
from reporting.provider.all.openshift.models import OCPAllCostLineItemProjectDailySummaryP
from reporting.provider.all.openshift.models import OCPAllCostSummaryByAccountPT
from reporting.provider.all.openshift.models import OCPAllCostSummaryByRegionPT
from reporting.provider.all.openshift.models import OCPAllCostSummaryByServicePT
from reporting.provider.all.openshift.models import OCPAllCostSummaryPT
from reporting.provider.all.openshift.models import OCPAllDatabaseSummaryPT
from reporting.provider.all.openshift.models import OCPAllNetworkSummaryPT
from reporting.provider.all.openshift.models import OCPAllStorageSummaryPT
from reporting.provider.aws.models import AWSAccountAlias
from reporting.provider.aws.models import AWSComputeSummaryByAccountP
from reporting.provider.aws.models import AWSComputeSummaryP
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostSummaryByAccountP
from reporting.provider.aws.models import AWSCostSummaryByRegionP
from reporting.provider.aws.models import AWSCostSummaryByServiceP
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.aws.models import AWSDatabaseSummaryP
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.models import AWSNetworkSummaryP
from reporting.provider.aws.models import AWSOrganizationalUnit
from reporting.provider.aws.models import AWSStorageSummaryByAccountP
from reporting.provider.aws.models import AWSStorageSummaryP
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSComputeSummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemDailySummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByAccountP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByRegionP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByServiceP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryP
from reporting.provider.aws.openshift.models import OCPAWSDatabaseSummaryP
from reporting.provider.aws.openshift.models import OCPAWSNetworkSummaryP
from reporting.provider.aws.openshift.models import OCPAWSStorageSummaryP
from reporting.provider.aws.openshift.models import OCPAWSTagsSummary
from reporting.provider.azure.models import AzureComputeSummaryP
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureCostSummaryByAccountP
from reporting.provider.azure.models import AzureCostSummaryByLocationP
from reporting.provider.azure.models import AzureCostSummaryByServiceP
from reporting.provider.azure.models import AzureCostSummaryP
from reporting.provider.azure.models import AzureDatabaseSummaryP
from reporting.provider.azure.models import AzureNetworkSummaryP
from reporting.provider.azure.models import AzureStorageSummaryP
from reporting.provider.azure.models import AzureTagsSummary
from reporting.provider.azure.openshift.models import OCPAzureComputeSummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemDailySummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByAccountP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByLocationP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByServiceP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryP
from reporting.provider.azure.openshift.models import OCPAzureDatabaseSummaryP
from reporting.provider.azure.openshift.models import OCPAzureNetworkSummaryP
from reporting.provider.azure.openshift.models import OCPAzureStorageSummaryP
from reporting.provider.azure.openshift.models import OCPAzureTagsSummary
from reporting.provider.gcp.models import GCPComputeSummaryByAccountP
from reporting.provider.gcp.models import GCPComputeSummaryP
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByProjectP
from reporting.provider.gcp.models import GCPCostSummaryByRegionP
from reporting.provider.gcp.models import GCPCostSummaryByServiceP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.provider.gcp.models import GCPDatabaseSummaryP
from reporting.provider.gcp.models import GCPNetworkSummaryP
from reporting.provider.gcp.models import GCPStorageSummaryByAccountP
from reporting.provider.gcp.models import GCPStorageSummaryByProjectP
from reporting.provider.gcp.models import GCPStorageSummaryByRegionP
from reporting.provider.gcp.models import GCPStorageSummaryByServiceP
from reporting.provider.gcp.models import GCPStorageSummaryP
from reporting.provider.gcp.models import GCPTagsSummary
from reporting.provider.gcp.openshift.models import OCPGCPComputeSummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostLineItemDailySummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryByAccountP
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryByGCPProjectP
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryByRegionP
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryByServiceP
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryP
from reporting.provider.gcp.openshift.models import OCPGCPDatabaseSummaryP
from reporting.provider.gcp.openshift.models import OCPGCPNetworkSummaryP
from reporting.provider.gcp.openshift.models import OCPGCPStorageSummaryP
from reporting.provider.gcp.openshift.models import OCPGCPTagsSummary
from reporting.provider.models import SubsIDMap
from reporting.provider.models import SubsLastProcessed
from reporting.provider.models import TenantAPIProvider
from reporting.provider.ocp.costs.models import CostSummary
from reporting.provider.ocp.models import OCPCostSummaryByNodeP
from reporting.provider.ocp.models import OCPCostSummaryByProjectP
from reporting.provider.ocp.models import OCPCostSummaryP
from reporting.provider.ocp.models import OCPPodSummaryByProjectP
from reporting.provider.ocp.models import OCPPodSummaryP
from reporting.provider.ocp.models import OCPStorageVolumeLabelSummary
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsagePodLabelSummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import OCPVolumeSummaryByProjectP
from reporting.provider.ocp.models import OCPVolumeSummaryP
from reporting.user_settings.models import UserSettings

# These are partitioned tables
OCP_ON_ALL_PERSPECTIVES = (
    OCPAllCostSummaryPT,
    OCPAllCostSummaryByAccountPT,
    OCPAllCostSummaryByServicePT,
    OCPAllCostSummaryByRegionPT,
    OCPAllComputeSummaryPT,
    OCPAllDatabaseSummaryPT,
    OCPAllNetworkSummaryPT,
    OCPAllStorageSummaryPT,
)

# These are partitioned tables
OCP_ON_AWS_PERSPECTIVES = (
    OCPAWSComputeSummaryP,
    OCPAWSCostSummaryP,
    OCPAWSCostSummaryByAccountP,
    OCPAWSCostSummaryByServiceP,
    OCPAWSCostSummaryByRegionP,
    OCPAWSDatabaseSummaryP,
    OCPAWSNetworkSummaryP,
    OCPAWSStorageSummaryP,
)

# These are partitioned tables
OCP_ON_AZURE_PERSPECTIVES = (
    OCPAzureCostSummaryP,
    OCPAzureCostSummaryByAccountP,
    OCPAzureCostSummaryByServiceP,
    OCPAzureCostSummaryByLocationP,
    OCPAzureComputeSummaryP,
    OCPAzureStorageSummaryP,
    OCPAzureNetworkSummaryP,
    OCPAzureDatabaseSummaryP,
)

# These are cleaned during source delete
# Table name differs based on ONPREM to avoid collision in PostgreSQL
if getattr(settings, "ONPREM", False):
    TRINO_MANAGED_TABLES = {
        "reporting_ocpusagelineitem_daily_summary_trino": "source",
        "managed_gcp_openshift_daily_temp": "ocp_source",
        "managed_gcp_openshift_disk_capacities_temp": "ocp_source",
        "managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp": "ocp_source",
        "managed_reporting_ocpgcpcostlineitem_project_daily_summary": "ocp_source",
        "managed_aws_openshift_daily_temp": "ocp_source",
        "managed_reporting_ocpawscostlineitem_project_daily_summary_temp": "ocp_source",
        "managed_reporting_ocpawscostlineitem_project_daily_summary": "ocp_source",
        "managed_aws_openshift_disk_capacities_temp": "ocp_source",
        "managed_azure_openshift_daily_temp": "ocp_source",
        "managed_azure_openshift_disk_capacities_temp": "ocp_source",
        "managed_reporting_ocpazurecostlineitem_project_daily_summary_temp": "ocp_source",
        "managed_reporting_ocpazurecostlineitem_project_daily_summary": "ocp_source",
    }
else:
    TRINO_MANAGED_TABLES = {
        "reporting_ocpusagelineitem_daily_summary": "source",
        "managed_gcp_openshift_daily_temp": "ocp_source",
        "managed_gcp_openshift_disk_capacities_temp": "ocp_source",
        "managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp": "ocp_source",
        "managed_reporting_ocpgcpcostlineitem_project_daily_summary": "ocp_source",
        "managed_aws_openshift_daily_temp": "ocp_source",
        "managed_reporting_ocpawscostlineitem_project_daily_summary_temp": "ocp_source",
        "managed_reporting_ocpawscostlineitem_project_daily_summary": "ocp_source",
        "managed_aws_openshift_disk_capacities_temp": "ocp_source",
        "managed_azure_openshift_daily_temp": "ocp_source",
        "managed_azure_openshift_disk_capacities_temp": "ocp_source",
        "managed_reporting_ocpazurecostlineitem_project_daily_summary_temp": "ocp_source",
        "managed_reporting_ocpazurecostlineitem_project_daily_summary": "ocp_source",
    }

# These are cleaned during expired_data flow
if getattr(settings, "ONPREM", False):
    EXPIRE_MANAGED_TABLES = {
        "reporting_ocpusagelineitem_daily_summary_trino": "source",
    }
else:
    EXPIRE_MANAGED_TABLES = {
        "reporting_ocpusagelineitem_daily_summary": "source",
    }
