#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Models for cost entry tables."""
# flake8: noqa
# pylint: disable=unused-import
from reporting.provider.all.openshift.models import OCPAllCostLineItemDailySummary
from reporting.provider.all.openshift.models import OCPAllCostLineItemProjectDailySummary
from reporting.provider.aws.models import AWSAccountAlias
from reporting.provider.aws.models import AWSComputeSummary
from reporting.provider.aws.models import AWSComputeSummaryByAccount
from reporting.provider.aws.models import AWSComputeSummaryByRegion
from reporting.provider.aws.models import AWSComputeSummaryByService
from reporting.provider.aws.models import AWSCostEntry
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItem
from reporting.provider.aws.models import AWSCostEntryLineItemDaily
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryPricing
from reporting.provider.aws.models import AWSCostEntryProduct
from reporting.provider.aws.models import AWSCostEntryReservation
from reporting.provider.aws.models import AWSCostSummary
from reporting.provider.aws.models import AWSCostSummaryByAccount
from reporting.provider.aws.models import AWSCostSummaryByRegion
from reporting.provider.aws.models import AWSCostSummaryByService
from reporting.provider.aws.models import AWSDatabaseSummary
from reporting.provider.aws.models import AWSNetworkSummary
from reporting.provider.aws.models import AWSStorageSummary
from reporting.provider.aws.models import AWSStorageSummaryByAccount
from reporting.provider.aws.models import AWSStorageSummaryByRegion
from reporting.provider.aws.models import AWSStorageSummaryByService
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDaily
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureCostEntryProductService
from reporting.provider.azure.models import AzureMeter
from reporting.provider.azure.models import AzureTagsSummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummary
from reporting.provider.ocp.costs.models import CostSummary  # noqa: F401
from reporting.provider.ocp.models import OCPStorageLineItem
from reporting.provider.ocp.models import OCPStorageLineItemDaily
from reporting.provider.ocp.models import OCPStorageVolumeLabelSummary
from reporting.provider.ocp.models import OCPUsageLineItem
from reporting.provider.ocp.models import OCPUsageLineItemDaily
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsagePodLabelSummary
from reporting.provider.ocp.models import OCPUsageReport
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp_aws.models import OCPAWSCostLineItemDailySummary
from reporting.provider.ocp_aws.models import OCPAWSCostLineItemProjectDailySummary


AWS_MATERIALIZED_VIEWS = (
    AWSComputeSummary,
    AWSComputeSummaryByAccount,
    AWSComputeSummaryByRegion,
    AWSComputeSummaryByService,
    AWSCostSummary,
    AWSCostSummaryByAccount,
    AWSCostSummaryByRegion,
    AWSCostSummaryByService,
    AWSDatabaseSummary,
    AWSNetworkSummary,
    AWSStorageSummary,
    AWSStorageSummaryByAccount,
    AWSStorageSummaryByRegion,
    AWSStorageSummaryByService,
)

OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS = (OCPAllCostLineItemDailySummary, OCPAllCostLineItemProjectDailySummary)
