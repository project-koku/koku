#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCP on AWS tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

# from django.db.models.functions import Upper


UI_SUMMARY_TABLES = (
    "reporting_ocpaws_compute_summary_p",
    "reporting_ocpaws_cost_summary_p",
    "reporting_ocpaws_cost_summary_by_account_p",
    "reporting_ocpaws_cost_summary_by_region_p",
    "reporting_ocpaws_cost_summary_by_service_p",
    "reporting_ocpaws_database_summary_p",
    "reporting_ocpaws_network_summary_p",
    "reporting_ocpaws_storage_summary_p",
)


class OCPAWSTagsValues(models.Model):
    class Meta:
        """Meta for OCPAWSTagsValues."""

        db_table = "reporting_ocpawstags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="ocp_aws_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    usage_account_ids = ArrayField(models.TextField())
    account_aliases = ArrayField(models.TextField())
    cluster_ids = ArrayField(models.TextField())
    cluster_aliases = ArrayField(models.TextField())
    namespaces = ArrayField(models.TextField())
    nodes = ArrayField(models.TextField(), null=True)


class OCPAWSTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPUsageTagSummary."""

        db_table = "reporting_ocpawstags_summary"
        unique_together = ("key", "cost_entry_bill", "report_period", "usage_account_id", "namespace", "node")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.CharField(max_length=253)
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    usage_account_id = models.CharField(max_length=50, null=True)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)
    namespace = models.TextField()
    node = models.TextField(null=True)


class OCPAWSCategorySummary(models.Model):
    """A collection of all current existing AWS category key and values for OCP on AWS."""

    class Meta:
        """Meta for OCPAWSCategorySummary."""

        db_table = "reporting_ocpawscategory_summary"
        unique_together = ("key", "cost_entry_bill", "usage_account_id")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)
    usage_account_id = models.TextField(null=True)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)


# ======================================================
#  Partitioned Models to replace matviews
# ======================================================


class OCPAWSCostSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSCostSummaryP."""

        db_table = "reporting_ocpaws_cost_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocpawscostsumm_usst")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSCostSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSCostSummaryByAccountP."""

        db_table = "reporting_ocpaws_cost_summary_by_account_p"
        indexes = [models.Index(fields=["usage_start"], name="ocpawscostsumm_acct_usst")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSCostSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSCostSummaryByServiceP."""

        db_table = "reporting_ocpaws_cost_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpawscostsumm_svc_usst"),
            models.Index(fields=["product_code"], name="ocpawscostsumm_svc_prod_cd"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    product_code = models.TextField(null=False)
    product_family = models.CharField(max_length=150, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSCostSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSCostSummaryByRegionP."""

        db_table = "reporting_ocpaws_cost_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpawscostsumm_reg_usst"),
            models.Index(fields=["region"], name="ocpawscostsumm_reg_region"),
            models.Index(fields=["availability_zone"], name="ocpawscostsumm_reg_zone"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    region = models.CharField(max_length=50, null=True)
    availability_zone = models.CharField(max_length=50, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSComputeSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSComputeSummaryP."""

        db_table = "reporting_ocpaws_compute_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpawscompsumm_usst"),
            models.Index(fields=["instance_type"], name="ocpawscompsumm_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    resource_id = models.CharField(max_length=253, null=True)
    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSStorageSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSStorageSummaryP."""

        db_table = "reporting_ocpaws_storage_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpawsstorsumm_usst"),
            models.Index(fields=["product_family"], name="ocpawsstorsumm_product_fam"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    product_family = models.CharField(max_length=150, null=True)
    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSNetworkSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSNetworkSummaryP."""

        db_table = "reporting_ocpaws_network_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpawsnetsumm_usst"),
            models.Index(fields=["product_code"], name="ocpawsnetsumm_product_cd"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    product_code = models.TextField(null=False)
    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSDatabaseSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSDatabaseSummaryP."""

        db_table = "reporting_ocpaws_database_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpawsdbsumm_usst"),
            models.Index(fields=["product_code"], name="ocpawsdbsumm_product_cd"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)
    product_code = models.TextField(null=False)
    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSCostLineItemDailySummaryP(models.Model):
    """A summarized partitioned table of OCP on AWS cost."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class DeferredSQL:
        create_sql = [
            ("""DROP INDEX IF EXISTS "p_ix_ocpaws_prodfam_ilike" ;""", None),
            (
                """CREATE INDEX "p_ix_ocpaws_prodfam_ilike"
    ON "reporting_ocpawscostlineitem_daily_summary_p"
 USING GIN ((upper("product_family")) gin_trgm_ops) ;""",
                None,
            ),
            ("""DROP INDEX IF EXISTS "p_ix_ocpaws_prodcode_ilike" ;""", None),
            (
                """CREATE INDEX "p_ix_ocpaws_prodcode_ilike"
    ON "reporting_ocpawscostlineitem_daily_summary_p"
 USING GIN ((upper("product_code")) gin_trgm_ops) ;""",
                None,
            ),
        ]

    class Meta:
        """Meta for OCPAWSCostLineItemDailySummaryP."""

        db_table = "reporting_ocpawscostlineitem_daily_summary_p"

        indexes = [
            models.Index(fields=["usage_start"], name="p_cost_sum_ocpaws_use_idx"),
            models.Index(fields=["namespace"], name="p_cost_sum_ocpaws_nspc_idx"),
            models.Index(fields=["node"], name="p_cost_sum_ocpaws_nde_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="p_cost_sum_ocpaws_rsrc_idx"),
            GinIndex(fields=["tags"], name="p_cost_ocpaws_tags_idx"),
            models.Index(fields=["product_family"], name="p_ocpaws_prod_fam_idx"),
            models.Index(fields=["instance_type"], name="p_ocpaws_inst_typ_idx"),
            # The next 2 would only work for Django 4
            # GinIndex(Upper("product_family"), opclasses=["gin_trgm_ops"], name="p_ix_ocp_aws_product_family_ilike"),
            # GinIndex(Upper("product_code"), opclasses=["gin_trgm_ops"], name="p_ix_ocp_aws_product_code_ilike"),
            # A GIN functional index named "ix_ocp_aws_product_family_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_family) gin_trgm_ops)
            # A GIN functional index named "ix_ocp_aws_product_code_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_code) gin_trgm_ops)
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    # OCP Fields
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = ArrayField(models.CharField(max_length=253, null=False))
    node = models.CharField(max_length=253, null=True)
    resource_id = models.CharField(max_length=253, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    # AWS Fields
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, null=True)
    product_code = models.TextField(null=False)
    product_family = models.CharField(max_length=150, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)
    availability_zone = models.CharField(max_length=50, null=True)
    region = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
    tags = JSONField(null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    normalized_usage_amount = models.FloatField(null=True)
    currency_code = models.CharField(max_length=10, null=True)
    # Cost breakdown can be done by cluster, node, project.
    # Cluster and node cost can be determined by summing the AWS unblended_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(unblended_cost) - sum(project_cost)
    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)
    # A JSON dictionary of the project cost, keyed by project/namespace name
    # See comment on unblended_cost for project cost explanation
    project_costs = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)


class OCPAWSCostLineItemProjectDailySummaryP(models.Model):
    """A summarized partitioned table of OCP on AWS cost by OpenShift project."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAWSCostLineItemProjectDailySummaryP."""

        db_table = "reporting_ocpawscostlineitem_project_daily_summary_p"

        indexes = [
            models.Index(fields=["usage_start"], name="p_cost_prj_sum_ocp_use_idx"),
            models.Index(fields=["namespace"], name="p_cost_prj_sum_nspc_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="p_cost_prj_sum_nd_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="p_cost_prj_sum_rsrc_idx"),
            GinIndex(fields=["pod_labels"], name="p_cost_prj_pod_lbls_idx"),
            GinIndex(fields=["aws_cost_category"], name="aws_cost_category_idx"),
            models.Index(fields=["product_family"], name="p_ocpaws_prj_prd_fam_idx"),
            models.Index(fields=["instance_type"], name="p_ocpaws_prj_inst_typ_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    # OCP Fields
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)
    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    persistentvolume = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=50, null=True)
    pod_labels = JSONField(null=True)
    resource_id = models.CharField(max_length=253, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    # AWS Fields
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, null=True)
    product_code = models.TextField(null=False)
    product_family = models.CharField(max_length=150, null=True)
    infrastructure_data_in_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_out_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    data_transfer_direction = models.TextField(null=True)
    instance_type = models.CharField(max_length=50, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)
    availability_zone = models.CharField(max_length=50, null=True)
    region = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    normalized_usage_amount = models.FloatField(null=True)
    currency_code = models.CharField(max_length=10, null=True)
    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    blended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    tags = JSONField(null=True)
    aws_cost_category = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
