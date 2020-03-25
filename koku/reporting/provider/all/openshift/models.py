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
"""Models for OCP on AWS tables."""
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class OCPAllCostLineItemDailySummary(models.Model):
    """A summarized view of OCP on All infrastructure cost."""

    class Meta:
        """Meta for OCPAllCostLineItemDailySummary."""

        db_table = "reporting_ocpallcostlineitem_daily_summary"
        managed = False

        indexes = [
            models.Index(fields=["usage_start"], name="ocpall_usage_idx"),
            GinIndex(fields=["namespace"], name="ocpall_namespace_idx"),
            models.Index(fields=["node"], name="ocpall_node_idx", opclasses=["varcahr_pattern_ops"]),
            models.Index(fields=["resource_id"], name="ocpall_resource_idx"),
            GinIndex(fields=["tags"], name="ocpall_tags_idx"),
            models.Index(fields=["product_family"], name="ocpall_product_family_idx"),
            models.Index(fields=["instance_type"], name="ocpall_instance_type_idx"),
        ]

    id = models.IntegerField(primary_key=True)

    # The infrastructure provider type
    source_type = models.TextField()

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = ArrayField(models.TextField(null=False))

    node = models.CharField(max_length=253, null=False)

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

    # A JSON dictionary of the project cost, keyed by project/namespace name
    # See comment on unblended_cost for project cost explanation
    project_costs = JSONField(null=True)


class OCPAllCostLineItemDailySummaryCompute(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the compute service category."""

    class Meta:
        """Meta for OCPAllCostLineItemDailySummaryCompute."""

        db_table = "reporting_ocpallcostlineitem_daily_summary_compute"
        managed = False

    id = models.IntegerField(primary_key=True)

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemDailySummaryNetwork(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the network service category."""

    class Meta:
        """Meta for OCPAllCostLineItemDailySummaryNetwork."""

        db_table = "reporting_ocpallcostlineitem_daily_summary_network"
        managed = False

    id = models.IntegerField(primary_key=True)

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemDailySummaryStorage(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the storage service category."""

    class Meta:
        """Meta for OCPAllCostLineItemDailySummaryStorage."""

        db_table = "reporting_ocpallcostlineitem_daily_summary_storage"
        managed = False

    id = models.IntegerField(primary_key=True)

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemDailySummaryDatabase(models.Model):
    """A summarized view of OCP on All infrastructure cost for products in the database service category."""

    class Meta:
        """Meta for OCPAllCostLineItemDailySummaryDatabase."""

        db_table = "reporting_ocpallcostlineitem_daily_summary_database"
        managed = False

    id = models.IntegerField(primary_key=True)

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


# ===============
#  Project views
# ===============


class OCPAllCostLineItemProjectDailySummary(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project."""

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummary."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary"
        managed = False

        indexes = [
            models.Index(fields=["usage_start"], name="ocpall_proj_usage_idx"),
            models.Index(fields=["namespace"], name="ocpall_proj_namespace_idx"),
            models.Index(fields=["product_code"], name="ocpall_proj_prod_code_idx"),
        ]

    id = models.IntegerField(primary_key=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemProjectDailySummaryCompute(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project for products in the compute service category."""

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummaryCompute."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary_compute"
        managed = False

    id = models.IntegerField(primary_key=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemProjectDailySummaryDatabase(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project for products in the database service category."""

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummaryDatabase."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary_database"
        managed = False

    id = models.IntegerField(primary_key=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemProjectDailySummaryNetwork(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project for products in the network service category."""

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummaryNetwork."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary_network"
        managed = False

    id = models.IntegerField(primary_key=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)


class OCPAllCostLineItemProjectDailySummaryStorage(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project for products in the storage service category."""

    class Meta:
        """Meta for OCPAllCostLineItemProjectDailySummaryStorage."""

        db_table = "reporting_ocpallcostlineitem_project_daily_summary_storage"
        managed = False

    id = models.IntegerField(primary_key=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    usage_amount = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    project_markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    pod_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10, null=True)
