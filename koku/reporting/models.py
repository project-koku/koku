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

# pylint: disable=unused-import
from reporting.provider.all.openshift.models import (OCPAllCostLineItemDailySummary,         # noqa: F401
                                                     OCPAllCostLineItemProjectDailySummary)  # noqa: F401
from reporting.provider.aws.models import (AWSAccountAlias,                       # noqa: F401
                                           AWSComputeSummary,                     # noqa: F401
                                           AWSComputeSummaryByAccount,            # noqa: F401
                                           AWSComputeSummaryByRegion,             # noqa: F401
                                           AWSComputeSummaryByService,            # noqa: F401
                                           AWSCostEntry,                          # noqa: F401
                                           AWSCostEntryBill,                      # noqa: F401
                                           AWSCostEntryLineItem,                  # noqa: F401
                                           AWSCostEntryLineItemDaily,             # noqa: F401
                                           AWSCostEntryLineItemDailySummary,      # noqa: F401
                                           AWSCostEntryPricing,                   # noqa: F401
                                           AWSCostEntryProduct,                   # noqa: F401
                                           AWSCostEntryReservation,               # noqa: F401
                                           AWSCostSummary,                        # noqa: F401
                                           AWSCostSummaryByAccount,               # noqa: F401
                                           AWSCostSummaryByRegion,                # noqa: F401
                                           AWSCostSummaryByService,               # noqa: F401
                                           AWSDatabaseSummary,                    # noqa: F401
                                           AWSNetworkSummary,                     # noqa: F401
                                           AWSStorageSummary,                     # noqa: F401
                                           AWSStorageSummaryByAccount,            # noqa: F401
                                           AWSStorageSummaryByRegion,             # noqa: F401
                                           AWSStorageSummaryByService)            # noqa: F401
from reporting.provider.azure.models import (AzureCostEntryBill,                  # noqa: F401
                                             AzureCostEntryLineItemDaily,         # noqa: F401
                                             AzureCostEntryLineItemDailySummary,  # noqa: F401
                                             AzureCostEntryProductService,        # noqa: F401
                                             AzureMeter,                          # noqa: F401
                                             AzureTagsSummary)                    # noqa: F401
from reporting.provider.azure.openshift.models import (OCPAzureCostLineItemDailySummary,         # noqa: F401
                                                       OCPAzureCostLineItemProjectDailySummary)  # noqa: F401
from reporting.provider.ocp.costs.models import CostSummary                       # noqa: F401
from reporting.provider.ocp.models import (OCPStorageLineItem,                    # noqa: F401
                                           OCPStorageLineItemDaily,               # noqa: F401
                                           OCPUsageLineItem,                      # noqa: F401
                                           OCPUsageLineItemDaily,                 # noqa: F401
                                           OCPUsageLineItemDailySummary,          # noqa: F401
                                           OCPUsagePodLabelSummary,               # noqa: F401
                                           OCPUsageReport,                        # noqa: F401
                                           OCPUsageReportPeriod)                  # noqa: F401
from reporting.provider.ocp_aws.models import (OCPAWSCostLineItemDailySummary,    # noqa: F401
                                               OCPAWSCostLineItemProjectDailySummary)  # noqa: F401


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
    AWSStorageSummaryByService
)

OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS = (
    OCPAllCostLineItemDailySummary,
    OCPAllCostLineItemProjectDailySummary
)
