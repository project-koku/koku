#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for cost entry tables."""

from reporting.provider.all.openshift.models import OCPAllComputeSummaryPT
from reporting.provider.all.openshift.models import OCPAllCostSummaryByAccountPT
from reporting.provider.all.openshift.models import OCPAllCostSummaryByRegionPT
from reporting.provider.all.openshift.models import OCPAllCostSummaryByServicePT
from reporting.provider.all.openshift.models import OCPAllCostSummaryPT
from reporting.provider.all.openshift.models import OCPAllDatabaseSummaryPT
from reporting.provider.all.openshift.models import OCPAllNetworkSummaryPT
from reporting.provider.all.openshift.models import OCPAllStorageSummaryPT
from reporting.provider.aws.openshift.models import OCPAWSComputeSummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByAccountP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByRegionP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByServiceP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryP
from reporting.provider.aws.openshift.models import OCPAWSDatabaseSummaryP
from reporting.provider.aws.openshift.models import OCPAWSNetworkSummaryP
from reporting.provider.aws.openshift.models import OCPAWSStorageSummaryP
from reporting.provider.azure.openshift.models import OCPAzureComputeSummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByAccountP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByLocationP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByServiceP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryP
from reporting.provider.azure.openshift.models import OCPAzureDatabaseSummaryP
from reporting.provider.azure.openshift.models import OCPAzureNetworkSummaryP
from reporting.provider.azure.openshift.models import OCPAzureStorageSummaryP


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
TRINO_MANAGED_TABLES = {
    "reporting_ocpusagelineitem_daily_summary": "source",
    "reporting_ocpawscostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpawscostlineitem_project_daily_summary_temp": "ocp_source",
    "aws_openshift_daily_resource_matched_temp": "ocp_source",
    "aws_openshift_daily_tag_matched_temp": "ocp_source",
    "azure_openshift_daily_resource_matched_temp": "ocp_source",
    "azure_openshift_daily_tag_matched_temp": "ocp_source",
    "reporting_ocpazurecostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpazurecostlineitem_project_daily_summary_temp": "ocp_source",
    "reporting_ocpgcpcostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpgcpcostlineitem_project_daily_summary_temp": "ocp_source",
    "gcp_openshift_daily_resource_matched_temp": "ocp_source",
    "gcp_openshift_daily_tag_matched_temp": "ocp_source",
    "managed_aws_openshift_daily": "ocp_source",
    "managed_azure_openshift_daily": "ocp_source",
    "managed_gcp_openshift_daily": "ocp_source",
}

# These are cleaned during expired_data flow
EXPIRE_MANAGED_TABLES = {
    "reporting_ocpusagelineitem_daily_summary": "source",
    "reporting_ocpawscostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpgcpcostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpazurecostlineitem_project_daily_summary": "ocp_source",
}

# TEMP tables are cleaned during day to day processing
OCP_ON_AWS_TEMP_MANAGED_TABLES = {
    "reporting_ocpawscostlineitem_project_daily_summary_temp",
    "aws_openshift_daily_resource_matched_temp",
    "aws_openshift_daily_tag_matched_temp",
    "aws_openshift_disk_capacities_temp",
}

OCP_ON_AZURE_TEMP_MANAGED_TABLES = {
    "reporting_ocpazurecostlineitem_project_daily_summary_temp",
    "azure_openshift_daily_resource_matched_temp",
    "azure_openshift_daily_tag_matched_temp",
    "azure_openshift_disk_capacities_temp",
}

OCP_ON_GCP_TEMP_MANAGED_TABLES = {
    "reporting_ocpgcpcostlineitem_project_daily_summary_temp",
    "gcp_openshift_daily_resource_matched_temp",
    "gcp_openshift_daily_tag_matched_temp",
}
