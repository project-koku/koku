#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for cost entry tables."""
# flake8: noqa
from reporting.currency.models import CurrencySettings
from reporting.partition.models import PartitionedTable
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
from reporting.provider.aws.models import AWSComputeSummaryByRegionP
from reporting.provider.aws.models import AWSComputeSummaryByServiceP
from reporting.provider.aws.models import AWSComputeSummaryP
from reporting.provider.aws.models import AWSCostEntry
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItem
from reporting.provider.aws.models import AWSCostEntryLineItemDaily
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryPricing
from reporting.provider.aws.models import AWSCostEntryProduct
from reporting.provider.aws.models import AWSCostEntryReservation
from reporting.provider.aws.models import AWSCostSummaryByAccountP
from reporting.provider.aws.models import AWSCostSummaryByRegionP
from reporting.provider.aws.models import AWSCostSummaryByServiceP
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.aws.models import AWSDatabaseSummaryP
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.aws.models import AWSNetworkSummaryP
from reporting.provider.aws.models import AWSOrganizationalUnit
from reporting.provider.aws.models import AWSStorageSummaryByAccountP
from reporting.provider.aws.models import AWSStorageSummaryByRegionP
from reporting.provider.aws.models import AWSStorageSummaryByServiceP
from reporting.provider.aws.models import AWSStorageSummaryP
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSComputeSummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemDailySummary
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummary
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
from reporting.provider.azure.models import AzureCostEntryLineItemDaily
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureCostEntryProductService
from reporting.provider.azure.models import AzureCostSummaryByAccountP
from reporting.provider.azure.models import AzureCostSummaryByLocationP
from reporting.provider.azure.models import AzureCostSummaryByServiceP
from reporting.provider.azure.models import AzureCostSummaryP
from reporting.provider.azure.models import AzureDatabaseSummaryP
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.azure.models import AzureMeter
from reporting.provider.azure.models import AzureNetworkSummaryP
from reporting.provider.azure.models import AzureStorageSummaryP
from reporting.provider.azure.models import AzureTagsSummary
from reporting.provider.azure.openshift.models import OCPAzureComputeSummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByAccountP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByLocationP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByServiceP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryP
from reporting.provider.azure.openshift.models import OCPAzureDatabaseSummaryP
from reporting.provider.azure.openshift.models import OCPAzureNetworkSummaryP
from reporting.provider.azure.openshift.models import OCPAzureStorageSummaryP
from reporting.provider.azure.openshift.models import OCPAzureTagsSummary
from reporting.provider.gcp.models import GCPComputeSummaryByAccountP
from reporting.provider.gcp.models import GCPComputeSummaryByProjectP
from reporting.provider.gcp.models import GCPComputeSummaryByRegionP
from reporting.provider.gcp.models import GCPComputeSummaryByServiceP
from reporting.provider.gcp.models import GCPComputeSummaryP
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPCostEntryProductService
from reporting.provider.gcp.models import GCPCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByProjectP
from reporting.provider.gcp.models import GCPCostSummaryByRegionP
from reporting.provider.gcp.models import GCPCostSummaryByServiceP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.provider.gcp.models import GCPDatabaseSummaryP
from reporting.provider.gcp.models import GCPEnabledTagKeys
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
from reporting.provider.ocp.costs.models import CostSummary
from reporting.provider.ocp.models import OCPCostSummaryByNodeP
from reporting.provider.ocp.models import OCPCostSummaryByProjectP
from reporting.provider.ocp.models import OCPCostSummaryP
from reporting.provider.ocp.models import OCPEnabledTagKeys
from reporting.provider.ocp.models import OCPNodeLabelLineItem
from reporting.provider.ocp.models import OCPNodeLabelLineItemDaily
from reporting.provider.ocp.models import OCPPodSummaryByProjectP
from reporting.provider.ocp.models import OCPPodSummaryP
from reporting.provider.ocp.models import OCPStorageLineItem
from reporting.provider.ocp.models import OCPStorageLineItemDaily
from reporting.provider.ocp.models import OCPStorageVolumeLabelSummary
from reporting.provider.ocp.models import OCPUsageLineItem
from reporting.provider.ocp.models import OCPUsageLineItemDaily
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsagePodLabelSummary
from reporting.provider.ocp.models import OCPUsageReport
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
