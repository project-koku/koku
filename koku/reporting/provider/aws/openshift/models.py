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

VIEWS = (
    "reporting_ocpaws_compute_summary",
    "reporting_ocpaws_cost_summary",
    "reporting_ocpaws_cost_summary_by_account",
    "reporting_ocpaws_cost_summary_by_region",
    "reporting_ocpaws_cost_summary_by_service",
    "reporting_ocpaws_storage_summary",
    "reporting_ocpaws_database_summary",
    "reporting_ocpaws_network_summary",
)


class OCPAWSCostLineItemDailySummary(models.Model):
    """A summarized view of OCP on AWS cost."""

    class Meta:
        """Meta for OCPAWSCostLineItemDailySummary."""

        db_table = "reporting_ocpawscostlineitem_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="cost_summary_ocp_usage_idx"),
            models.Index(fields=["namespace"], name="cost_summary_namespace_idx"),
            models.Index(fields=["node"], name="cost_summary_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="cost_summary_resource_idx"),
            GinIndex(fields=["tags"], name="cost_tags_idx"),
            models.Index(fields=["product_family"], name="ocp_aws_product_family_idx"),
            models.Index(fields=["instance_type"], name="ocp_aws_instance_type_idx"),
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

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    unit = models.CharField(max_length=63, null=True)

    tags = JSONField(null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    normalized_usage_amount = models.FloatField(null=True)

    currency_code = models.CharField(max_length=10, null=True)

    # Cost breakdown can be done by cluster, node, project.
    # Cluster and node cost can be determined by summing the AWS unblended_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(unblended_cost) - sum(project_cost)
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    # A JSON dictionary of the project cost, keyed by project/namespace name
    # See comment on unblended_cost for project cost explanation
    project_costs = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSCostLineItemProjectDailySummary(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project."""

    class Meta:
        """Meta for OCPAWSCostLineItemProjectDailySummary."""

        db_table = "reporting_ocpawscostlineitem_project_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="cost_proj_sum_ocp_usage_idx"),
            models.Index(fields=["namespace"], name="cost__proj_sum_namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="cost_proj_sum_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["resource_id"], name="cost_proj_sum_resource_idx"),
            GinIndex(fields=["pod_labels"], name="cost_proj_pod_labels_idx"),
            models.Index(fields=["product_family"], name="ocp_aws_proj_prod_fam_idx"),
            models.Index(fields=["instance_type"], name="ocp_aws_proj_inst_type_idx"),
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

    # AWS Fields
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    unit = models.CharField(max_length=63, null=True)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    normalized_usage_amount = models.FloatField(null=True)

    currency_code = models.CharField(max_length=10, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    tags = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


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


# Materialized Views for UI Reporting
class OCPAWSCostSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class Meta:
        """Meta for OCPAWSCostSummary."""

        db_table = "reporting_ocpaws_cost_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSCostSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for OCPAWSCostSummaryByAccount."""

        db_table = "reporting_ocpaws_cost_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSCostSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for OCPAWSCostSummaryByService."""

        db_table = "reporting_ocpaws_cost_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSCostSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class Meta:
        """Meta for OCPAWSCostSummaryByRegion."""

        db_table = "reporting_ocpaws_cost_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

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

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSComputeSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPAWSComputeSummary."""

        db_table = "reporting_ocpaws_compute_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

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

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSStorageSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class Meta:
        """Meta for OCPAWSStorageSummary."""

        db_table = "reporting_ocpaws_storage_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

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

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSNetworkSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class Meta:
        """Meta for OCPAWSNetworkSummary."""

        db_table = "reporting_ocpaws_network_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAWSDatabaseSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class Meta:
        """Meta for OCPAWSDatabaseSummary."""

        db_table = "reporting_ocpaws_database_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.DO_NOTHING, null=True)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)
