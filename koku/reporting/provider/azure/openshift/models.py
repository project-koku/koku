#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCP on Azure tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

# from django.db.models.functions import Upper


UI_SUMMARY_TABLES = (
    "reporting_ocpazure_compute_summary_p",
    "reporting_ocpazure_cost_summary_p",
    "reporting_ocpazure_cost_summary_by_account_p",
    "reporting_ocpazure_cost_summary_by_location_p",
    "reporting_ocpazure_cost_summary_by_service_p",
    "reporting_ocpazure_database_summary_p",
    "reporting_ocpazure_network_summary_p",
    "reporting_ocpazure_storage_summary_p",
)


class OCPAzureCostLineItemDailySummary(models.Model):
    """A summarized view of OCP on Azure cost."""

    class Meta:
        """Meta for OCPAzureCostLineItemDailySummary."""

        db_table = "reporting_ocpazurecostlineitem_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="ocpazure_usage_start_idx"),
            models.Index(fields=["namespace"], name="ocpazure_namespace_idx"),
            models.Index(fields=["node"], name="ocpazure_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="ocpazure_resource_idx"),
            GinIndex(fields=["tags"], name="ocpazure_tags_idx"),
            models.Index(fields=["service_name"], name="ocpazure_service_name_idx"),
            models.Index(fields=["instance_type"], name="ocpazure_instance_type_idx"),
            # A GIN functional index named "ix_ocpazure_service_name_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(service_name) gin_trgm_ops)
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

    # Azure Fields
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    subscription_guid = models.TextField(null=False)

    instance_type = models.TextField(null=True)

    service_name = models.TextField(null=True)

    resource_location = models.TextField(null=True)

    tags = JSONField(null=True)

    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    # Cost breakdown can be done by cluster, node, project, and pod.
    # Cluster and node cost can be determined by summing the Azure pretax_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(pretax_cost) - sum(project_cost)
    pretax_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    currency = models.TextField(null=True)

    unit_of_measure = models.TextField(null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    # A JSON dictionary of the project cost, keyed by project/namespace name
    # See comment on pretax_cost for project cost explanation
    project_costs = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureCostLineItemProjectDailySummary(models.Model):
    """A summarized view of OCP on Azure cost by OpenShift project."""

    class Meta:
        """Meta for OCPAzureCostLineItemProjectDailySummary."""

        db_table = "reporting_ocpazurecostlineitem_project_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="ocpazure_proj_usage_start_idx"),
            models.Index(fields=["namespace"], name="ocpazure_proj_namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="ocpazure_proj_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="ocpazure_proj_resource_id_idx"),
            GinIndex(fields=["pod_labels"], name="ocpazure_proj_pod_labels_idx"),
            models.Index(fields=["service_name"], name="ocpazure_proj_service_name_idx"),
            models.Index(fields=["instance_type"], name="ocpazure_proj_inst_type_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    # OCP Fields
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=True)

    persistentvolumeclaim = models.CharField(max_length=253, null=True)

    persistentvolume = models.CharField(max_length=253, null=True)

    storageclass = models.CharField(max_length=50, null=True)

    pod_labels = JSONField(null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # Azure Fields
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    subscription_guid = models.TextField(null=False)

    instance_type = models.TextField(null=True)

    service_name = models.TextField(null=True)

    resource_location = models.TextField(null=True)

    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit_of_measure = models.TextField(null=True)

    currency = models.TextField(null=True)

    pretax_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    project_markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    pod_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True)

    tags = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureTagsValues(models.Model):
    class Meta:
        """Meta for OCPAzureTagsValues."""

        db_table = "reporting_ocpazuretags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="ocp_azure_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    subscription_guids = ArrayField(models.TextField())
    cluster_ids = ArrayField(models.TextField())
    cluster_aliases = ArrayField(models.TextField())
    namespaces = ArrayField(models.TextField())
    nodes = ArrayField(models.TextField(), null=True)


class OCPAzureTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for AzureTagsSummary."""

        db_table = "reporting_ocpazuretags_summary"
        unique_together = ("key", "cost_entry_bill", "report_period", "subscription_guid", "namespace", "node")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.CharField(max_length=253)
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    subscription_guid = models.TextField(null=True)
    namespace = models.TextField()
    node = models.TextField(null=True)


# ======================================================
#  Partitioned Models to replace matviews
# ======================================================


class OCPAzureCostSummaryP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureCostSummaryP."""

        db_table = "reporting_ocpazure_cost_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocpazcostsumm_usage_start")]
        indexes = [models.Index(fields=["cluster_id"], name="ocpazcostsumm_clust_id")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureCostSummaryByAccountP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureCostSummaryByAccountP."""

        db_table = "reporting_ocpazure_cost_summary_by_account_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpazcostsumm_acc_usage_start"),
            models.Index(fields=["subscription_guid"], name="ocpazcostsumm_acc_sub_guid"),
            models.Index(fields=["cluster_id"], name="ocpazcostsumm_acc_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureCostSummaryByLocationP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by location.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureCostSummaryByLocationP."""

        db_table = "reporting_ocpazure_cost_summary_by_location_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpazcostsumm_loc_usage_start"),
            models.Index(fields=["resource_location"], name="ocpazcostsumm_loc_res_loc"),
            models.Index(fields=["cluster_id"], name="ocpazcostsumm_loc_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    resource_location = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureCostSummaryByServiceP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureCostSummaryByServiceP."""

        db_table = "reporting_ocpazure_cost_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpazcostsumm_svc_usage_start"),
            models.Index(fields=["service_name"], name="ocpazcostsumm_svc_svc_name"),
            models.Index(fields=["cluster_id"], name="ocpazcostsumm_svc_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureComputeSummaryP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureComputeSummaryP."""

        db_table = "reporting_ocpazure_compute_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpazcompsumm_usage_start"),
            models.Index(fields=["instance_type"], name="ocpazcompsumm_insttyp"),
            models.Index(fields=["cluster_id"], name="ocpazcompsumm_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    instance_type = models.TextField(null=True)
    resource_id = models.CharField(max_length=253, null=True)
    usage_quantity = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureStorageSummaryP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureStorageSummaryP."""

        db_table = "reporting_ocpazure_storage_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpazstorsumm_usage_start"),
            models.Index(fields=["service_name"], name="ocpazstorsumm_svc_name"),
            models.Index(fields=["cluster_id"], name="ocpazstorsumm_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=True)
    usage_quantity = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureNetworkSummaryP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureNetworkSummaryP."""

        db_table = "reporting_ocpazure_network_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpaznetsumm_usage_start"),
            models.Index(fields=["service_name"], name="ocpaznetsumm_svc_name"),
            models.Index(fields=["cluster_id"], name="ocpaznetsumm_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=True)
    usage_quantity = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureDatabaseSummaryP(models.Model):
    """A Summarized Partitioned table specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureDatabaseSummaryP."""

        db_table = "reporting_ocpazure_database_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpazdbsumm_usage_start"),
            models.Index(fields=["service_name"], name="ocpazdbsumm_svc_name"),
            models.Index(fields=["cluster_id"], name="ocpazdbsumm_clust_id"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=True)
    usage_quantity = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPAzureCostLineItemDailySummaryP(models.Model):
    """A summarized partitioned table of OCP on Azure cost."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class DeferredSQL:
        create_sql = [
            ("""DROP INDEX IF EXISTS "p_ix_ocpaz_svcnm_ilike" ;""", None),
            (
                """CREATE INDEX "p_ix_ocpaz_svcnm_ilike"
    ON "reporting_ocpazurecostlineitem_daily_summary_p"
 USING GIN ((upper("service_name")) gin_trgm_ops) ;""",
                None,
            ),
        ]

    class Meta:
        """Meta for OCPAzureCostLineItemDailySummaryP."""

        db_table = "reporting_ocpazurecostlineitem_daily_summary_p"

        indexes = [
            models.Index(fields=["usage_start"], name="p_ocpaz_use_strt_idx"),
            models.Index(fields=["namespace"], name="p_ocpaz_nspc_idx"),
            models.Index(fields=["node"], name="p_ocpaz_nde_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="p_ocpaz_rsrc_idx"),
            GinIndex(fields=["tags"], name="p_ocpaz_tags_idx"),
            models.Index(fields=["service_name"], name="p_ocpaz_svc_name_idx"),
            models.Index(fields=["instance_type"], name="p_ocpaz_inst_typ_idx"),
            # The next 1 would only work for Django 4
            # GinIndex(Upper("service_name"), opclasses=["gin_trgm_ops"], name="p_ix_ocpazure_service_name_ilike"),
            # A GIN functional index named "ix_ocpazure_service_name_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(service_name) gin_trgm_ops)
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

    # Azure Fields
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    subscription_guid = models.TextField(null=False)

    instance_type = models.TextField(null=True)

    service_name = models.TextField(null=True)

    resource_location = models.TextField(null=True)

    tags = JSONField(null=True)

    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    # Cost breakdown can be done by cluster, node, project, and pod.
    # Cluster and node cost can be determined by summing the Azure pretax_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(pretax_cost) - sum(project_cost)
    pretax_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    currency = models.TextField(null=True)

    unit_of_measure = models.TextField(null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    # A JSON dictionary of the project cost, keyed by project/namespace name
    # See comment on pretax_cost for project cost explanation
    project_costs = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureCostLineItemProjectDailySummaryP(models.Model):
    """A summarized parititoned table of OCP on Azure cost by OpenShift project."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPAzureCostLineItemProjectDailySummaryP."""

        db_table = "reporting_ocpazurecostlineitem_project_daily_summary_p"

        indexes = [
            models.Index(fields=["usage_start"], name="p_ocpaz_prj_use_strt_idx"),
            models.Index(fields=["namespace"], name="p_ocpaz_prj_nspc_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="p_ocpaz_prj_nde_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="p_ocpaz_prj_rsrc_idx"),
            GinIndex(fields=["pod_labels"], name="p_ocpaz_prj_pod_lbl_idx"),
            models.Index(fields=["service_name"], name="p_ocpaz_prj_srvc_name_idx"),
            models.Index(fields=["instance_type"], name="p_ocpaz_prj_inst_typ_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    # OCP Fields
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=True)

    persistentvolumeclaim = models.CharField(max_length=253, null=True)

    persistentvolume = models.CharField(max_length=253, null=True)

    storageclass = models.CharField(max_length=50, null=True)

    pod_labels = JSONField(null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # Azure Fields
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    subscription_guid = models.TextField(null=False)

    instance_type = models.TextField(null=True)

    service_name = models.TextField(null=True)

    resource_location = models.TextField(null=True)

    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit_of_measure = models.TextField(null=True)

    currency = models.TextField(null=True)

    pretax_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    project_markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    pod_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True)

    tags = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)
