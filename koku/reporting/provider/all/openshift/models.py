#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCP on AWS tables."""
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

# VIEWS is deprecated and will be removed in a future release
# It is currently only used in migrations that may still be in use.
VIEWS = (
    "reporting_ocpallcostlineitem_daily_summary",
    "reporting_ocpallcostlineitem_project_daily_summary",
    "reporting_ocpall_compute_summary",
    "reporting_ocpall_storage_summary",
    "reporting_ocpall_cost_summary",
    "reporting_ocpall_cost_summary_by_account",
    "reporting_ocpall_cost_summary_by_region",
    "reporting_ocpall_cost_summary_by_service",
    "reporting_ocpall_database_summary",
    "reporting_ocpall_network_summary",
)

OCP_ON_ALL_TABLES = (
    "reporting_ocpallcostlineitem_daily_summary_p",
    "reporting_ocpallcostlineitem_project_daily_summary_p",
)

UI_SUMMARY_TABLES = (
    "reporting_ocpall_cost_summary_pt",
    "reporting_ocpall_cost_summary_by_account_pt",
    "reporting_ocpall_cost_summary_by_service_pt",
    "reporting_ocpall_cost_summary_by_region_pt",
    "reporting_ocpall_compute_summary_pt",
    "reporting_ocpall_database_summary_pt",
    "reporting_ocpall_network_summary_pt",
    "reporting_ocpall_storage_summary_pt",
)


class OCPAllCostLineItemDailySummary(models.Model):
    """A summarized view of OCP on All infrastructure cost."""

    class Meta:
        """Meta for OCPAllCostLineItemDailySummary."""

        db_table = "reporting_ocpallcostlineitem_daily_summary"
        managed = False

        indexes = [
            models.Index(fields=["usage_start"], name="ocpall_usage_idx"),
            models.Index(fields=["namespace"], name="ocpall_namespace_idx"),
            models.Index(fields=["node"], name="ocpall_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="ocpall_resource_idx"),
            GinIndex(fields=["tags"], name="ocpall_tags_idx"),
            models.Index(fields=["product_family"], name="ocpall_product_family_idx"),
            models.Index(fields=["instance_type"], name="ocpall_instance_type_idx"),
            # A GIN functional index named "ocpall_product_code_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_code) gin_trgm_ops)
            # A GIN functional index named "ocpall_product_family_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_family) gin_trgm_ops)
        ]

    id = models.IntegerField(primary_key=True)

    # The infrastructure provider type
    source_type = models.TextField()

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = ArrayField(models.CharField(max_length=253, null=False))

    node = models.CharField(max_length=253, null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # Infrastructure source fields
    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    tags = JSONField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    # Cost breakdown can be done by cluster, node, project, and pod.
    # Cluster and node cost can be determined by summing the AWS unblended_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(unblended_cost) - sum(project_cost)
    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    source_uuid = models.UUIDField(unique=False, null=True)

    tags_hash = models.TextField(max_length=512)


class OCPAllCostLineItemProjectDailySummary(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project."""

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummary."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary"
        managed = False

        indexes = [
            models.Index(fields=["usage_start"], name="ocpall_proj_usage_idx"),
            models.Index(fields=["namespace"], name="ocpall_proj_namespace_idx"),
            models.Index(fields=["node"], name="ocpall_proj_node_idx"),
            models.Index(fields=["resource_id"], name="ocpall_proj_resource_idx"),
            GinIndex(fields=["pod_labels"], name="ocpall_proj_pod_labels_idx"),
            models.Index(fields=["product_family"], name="ocpall_proj_prod_fam_idx"),
            models.Index(fields=["instance_type"], name="ocpall_proj_inst_type_idx"),
        ]

    id = models.IntegerField(primary_key=True)

    # The infrastructure provider type
    source_type = models.TextField()

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=True)

    pod_labels = JSONField(null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # AWS Fields
    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


# ======================================================
#  Partitioned Models to replace matviews
# ======================================================


class OCPAllCostLineItemDailySummaryP(models.Model):
    """A summarized partitioned table of OCP on All infrastructure cost."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllCostLineItemDailySummary."""

        db_table = "reporting_ocpallcostlineitem_daily_summary_p"

        indexes = [
            models.Index(fields=["usage_start"], name="ocpall_p_usage_idx"),
            models.Index(fields=["namespace"], name="ocpall_p_namespace_idx"),
            models.Index(fields=["node"], name="ocpall_p_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="ocpall_p_resource_idx"),
            GinIndex(fields=["tags"], name="ocpall_p_tags_idx"),
            models.Index(fields=["product_family"], name="ocpall_p_product_family_idx"),
            models.Index(fields=["instance_type"], name="ocpall_p_instance_type_idx"),
            # A GIN functional index named "ocpall_product_code_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_code) gin_trgm_ops)
            # A GIN functional index named "ocpall_product_family_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_family) gin_trgm_ops)
        ]

    id = models.UUIDField(primary_key=True)

    # The infrastructure provider type
    source_type = models.TextField()

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = ArrayField(models.CharField(max_length=253, null=False))

    node = models.CharField(max_length=253, null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # Infrastructure source fields
    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    tags = JSONField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    # Cost breakdown can be done by cluster, node, project, and pod.
    # Cluster and node cost can be determined by summing the AWS unblended_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(unblended_cost) - sum(project_cost)
    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    source_uuid = models.ForeignKey("api.Provider", on_delete=models.CASCADE, db_column="source_uuid", null=True)


class OCPAllCostLineItemProjectDailySummaryP(models.Model):
    """A summarized partitioned table of OCP on AWS cost by OpenShift project."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummary."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary_p"

        indexes = [
            models.Index(fields=["usage_start"], name="ocpap_p_proj_usage_idx"),
            models.Index(fields=["namespace"], name="ocpap_p_proj_namespace_idx"),
            models.Index(fields=["node"], name="ocpap_p_proj_node_idx"),
            models.Index(fields=["resource_id"], name="ocpap_p_proj_resource_idx"),
            GinIndex(fields=["pod_labels"], name="ocpap_p_proj_pod_labels_idx"),
            models.Index(fields=["product_family"], name="ocpap_p_proj_prod_fam_idx"),
            models.Index(fields=["instance_type"], name="ocpap_p_proj_inst_type_idx"),
        ]

    id = models.UUIDField(primary_key=True)

    # The infrastructure provider type
    source_type = models.TextField()

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=True)

    pod_labels = JSONField(null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # AWS Fields
    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey("api.Provider", on_delete=models.CASCADE, db_column="source_uuid", null=True)


# ======================================================
#  Sub-tables to perspectives into summaries (partitioned)
# ======================================================


class OCPAllCostSummaryPT(models.Model):
    """A PARTITIONED TABLE specifically for UI API queries.
    This table gives a daily breakdown of total cost.
    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllCostSummary."""

        db_table = "reporting_ocpall_cost_summary_pt"
        indexes = [models.Index(fields=["cluster_id"], name="ocpap_costsumm_clust_ix")]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllCostSummaryByAccountPT(models.Model):
    """A PARTITIONED TABLE specifically for UI API queries.
    This table gives a daily breakdown of total cost by account.
    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllCostSummaryByAccount."""

        db_table = "reporting_ocpall_cost_summary_by_account_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_costsumm_acct_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_costsumm_acct_acctid_ix"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllCostSummaryByServicePT(models.Model):
    """A PARTITIONED TABLE specifically for UI API queries.
    This table gives a daily breakdown of total cost by account.
    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllCostSummaryByService."""

        db_table = "reporting_ocpall_cost_summary_by_service_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_costsumm_srv_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_costsumm_srv_acctid_ix"),
            models.Index(fields=["product_code"], name="ocpap_costsumm_srv_procode_ix"),
            models.Index(fields=["product_family"], name="ocpap_costsumm_srv_profam_ix"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllCostSummaryByRegionPT(models.Model):
    """A PARTITIONED TABLE specifically for UI API queries.
    This table gives a daily breakdown of total cost by region.
    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllCostSummaryByRegion."""

        db_table = "reporting_ocpall_cost_summary_by_region_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_costsumm_rgn_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_costsumm_rgn_acctid_ix"),
            models.Index(fields=["region"], name="ocpap_costsumm_rgn_region_ix"),
            models.Index(fields=["availability_zone"], name="ocpap_costsumm_rgn_avail_zn_ix"),
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

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllComputeSummaryPT(models.Model):
    """A summarized partitioned table of OCP on All infrastructure cost for products in the compute service category."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllComputeSummary."""

        db_table = "reporting_ocpall_compute_summary_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_acctid_ix"),
            models.Index(fields=["product_code"], name="ocpap_cmpsumm_procode_ix"),
            models.Index(fields=["instance_type"], name="ocpap_cmpsumm_inst_typ_ix"),
            models.Index(fields=["resource_id"], name="ocpap_cmpsumm_rsrc_id_ix"),
        ]

    id = models.UUIDField(primary_key=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    instance_type = models.CharField(max_length=50)

    resource_id = models.CharField(max_length=253)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllDatabaseSummaryPT(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the database service category."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllDatabaseSummary."""

        db_table = "reporting_ocpall_database_summary_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_db_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_db_acctid_ix"),
            models.Index(fields=["product_code"], name="ocpap_cmpsumm_db_procode_ix"),
        ]

    id = models.UUIDField(primary_key=True)

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllNetworkSummaryPT(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the network service category."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllNetworkSummary."""

        db_table = "reporting_ocpall_network_summary_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_net_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_net_acctid_ix"),
            models.Index(fields=["product_code"], name="ocpap_cmpsumm_net_procode_ix"),
        ]

    id = models.UUIDField(primary_key=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")


class OCPAllStorageSummaryPT(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the storage service category."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAllStorageSummary."""

        db_table = "reporting_ocpall_storage_summary_pt"
        indexes = [
            models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_stor_clust_ix"),
            models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_stor_acctid_ix"),
            models.Index(fields=["product_code"], name="ocpap_cmpsumm_stor_procode_ix"),
            models.Index(fields=["product_family"], name="ocpap_cmpsumm_stor_profam_ix"),
        ]

    id = models.UUIDField(primary_key=True)

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_family = models.CharField(max_length=150, null=True)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )

    source_type = models.TextField(default="")
