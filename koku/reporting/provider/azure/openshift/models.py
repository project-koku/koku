#
# Copyright 2019 Red Hat, Inc.
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
"""Models for OCP on Azure tables."""
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.db import models


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

    # OCP Fields
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = ArrayField(models.CharField(max_length=253, null=False))

    pod = ArrayField(models.CharField(max_length=253, null=False))

    node = models.CharField(max_length=253, null=False)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # Azure Fields
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    subscription_guid = models.CharField(max_length=50, null=False)

    instance_type = models.CharField(max_length=50, null=True)

    service_name = models.CharField(max_length=50, null=False)

    resource_location = models.CharField(max_length=50, null=False)

    tags = JSONField(null=True)

    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    # Cost breakdown can be done by cluster, node, project, and pod.
    # Cluster and node cost can be determined by summing the Azure pretax_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(pretax_cost) - sum(project_cost)
    pretax_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    offer_id = models.PositiveIntegerField(null=True)

    currency = models.CharField(max_length=10, null=False, default="USD")

    unit_of_measure = models.CharField(max_length=63, null=True)

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

    # OCP Fields
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=True)

    node = models.CharField(max_length=253, null=False)

    pod_labels = JSONField(null=True)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    # Azure Fields
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    subscription_guid = models.CharField(max_length=50, null=False)

    instance_type = models.CharField(max_length=50, null=True)

    service_name = models.CharField(max_length=50, null=False)

    resource_location = models.CharField(max_length=50, null=False)

    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit_of_measure = models.CharField(max_length=63, null=True)

    offer_id = models.PositiveIntegerField(null=True)

    currency = models.CharField(max_length=10, null=False, default="USD")

    pretax_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    project_markup_cost = models.DecimalField(max_digits=17, decimal_places=9, null=True)

    pod_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for AzureTagsSummary."""

        db_table = "reporting_ocpazuretags_summary"
        unique_together = ("key", "cost_entry_bill")

    id = models.BigAutoField(primary_key=True)

    key = models.CharField(max_length=253)
    values = ArrayField(models.CharField(max_length=253))
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)
    subscription_guid = ArrayField(models.CharField(max_length=50))
    namespace = ArrayField(models.CharField(max_length=253, null=False))


# Materialized Views for UI Reporting
class OCPAzureCostSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class Meta:
        """Meta for OCPAzureCostSummary."""

        db_table = "reporting_ocpazure_cost_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureCostSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for OCPAzureCostSummaryByService."""

        db_table = "reporting_ocpazure_cost_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    subscription_guid = models.CharField(max_length=50, null=False)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureCostSummaryByLocation(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by location.

    """

    class Meta:
        """Meta for OCPAzureCostSummaryByService."""

        db_table = "reporting_ocpazure_cost_summary_by_location"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    resource_location = models.CharField(max_length=50, null=False)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureCostSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class Meta:
        """Meta for OCPAzureCostSummaryByService."""

        db_table = "reporting_ocpazure_cost_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    service_name = models.TextField(null=False)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureComputeSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPAzureComputeSummary."""

        db_table = "reporting_ocpazure_compute_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    resource_id = models.CharField(max_length=253, null=True)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.CharField(max_length=63, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureStorageSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class Meta:
        """Meta for OCPAzureStorageSummary."""

        db_table = "reporting_ocpazure_storage_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    service_name = models.TextField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.CharField(max_length=63, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureNetworkSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class Meta:
        """Meta for OCPAzureNetworkSummary."""

        db_table = "reporting_ocpazure_network_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    service_name = models.TextField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.CharField(max_length=63, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)


class OCPAzureDatabaseSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class Meta:
        """Meta for OCPAzureDatabaseSummary."""

        db_table = "reporting_ocpazure_database_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    service_name = models.TextField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.CharField(max_length=63, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False, default="USD")
    source_uuid = models.UUIDField(unique=False, null=True)
