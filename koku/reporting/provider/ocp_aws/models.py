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

from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class OCPAWSUsageLineItemDaily(models.Model):
    """A daily view of OCP and AWS CPU and Memory usage."""

    class Meta:
        """Meta for OCPAWSUsageLineItemDaily."""

        db_table = 'reporting_ocpawsusagelineitem_daily'
        managed = False

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=False)

    # Another node identifier used to tie the node to an EC2 instance
    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateTimeField(null=False)

    usage_end = models.DateTimeField(null=False)

    pod_usage_cpu_core_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_request_cpu_core_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_limit_cpu_core_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_usage_memory_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_request_memory_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_limit_memory_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    node_capacity_cpu_cores = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    node_capacity_cpu_core_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    node_capacity_memory_bytes = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    node_capacity_memory_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    cluster_capacity_cpu_core_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    cluster_capacity_memory_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_labels = JSONField(null=True)

    # AWS Fields
    cost_entry_product = models.ForeignKey('AWSCostEntryProduct',
                                           on_delete=models.DO_NOTHING, null=True)

    cost_entry_pricing = models.ForeignKey('AWSCostEntryPricing',
                                           on_delete=models.DO_NOTHING, null=True)

    cost_entry_reservation = models.ForeignKey('AWSCostEntryReservation',
                                               on_delete=models.DO_NOTHING,
                                               null=True)

    line_item_type = models.CharField(max_length=50, null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_type = models.CharField(max_length=50, null=True)

    operation = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9,
                                       null=True)

    normalization_factor = models.FloatField(null=True)

    normalized_usage_amount = models.FloatField(null=True)

    currency_code = models.CharField(max_length=10)

    unblended_rate = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    unblended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    blended_rate = models.DecimalField(max_digits=17, decimal_places=9,
                                       null=True)

    blended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                       null=True)

    public_on_demand_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                                null=True)

    public_on_demand_rate = models.DecimalField(max_digits=17, decimal_places=9,
                                                null=True)

    tax_type = models.TextField(null=True)

    tags = JSONField(null=True)


class OCPAWSStorageLineItemDaily(models.Model):
    """A daily view of OCP and AWS storage usage."""

    class Meta:
        """Meta for OCPAWSStorageLineItemDaily."""

        db_table = 'reporting_ocpawsstoragelineitem_daily'
        managed = False

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=False)

    # Another node identifier used to tie the node to an EC2 instance
    resource_id = models.CharField(max_length=253, null=True)

    persistentvolumeclaim = models.CharField(max_length=253)

    persistentvolume = models.CharField(max_length=253)

    storageclass = models.CharField(max_length=50, null=True)

    usage_start = models.DateTimeField(null=False)

    usage_end = models.DateTimeField(null=False)

    persistentvolumeclaim_capacity_bytes = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    persistentvolumeclaim_capacity_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    volume_request_storage_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    persistentvolumeclaim_usage_byte_seconds = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    persistentvolume_labels = JSONField(null=True)

    persistentvolumeclaim_labels = JSONField(null=True)

    # AWS Fields
    cost_entry_product = models.ForeignKey('AWSCostEntryProduct',
                                           on_delete=models.DO_NOTHING, null=True)

    cost_entry_pricing = models.ForeignKey('AWSCostEntryPricing',
                                           on_delete=models.DO_NOTHING, null=True)

    cost_entry_reservation = models.ForeignKey('AWSCostEntryReservation',
                                               on_delete=models.DO_NOTHING,
                                               null=True)

    line_item_type = models.CharField(max_length=50, null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_type = models.CharField(max_length=50, null=True)

    operation = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9,
                                       null=True)

    normalization_factor = models.FloatField(null=True)

    normalized_usage_amount = models.FloatField(null=True)

    currency_code = models.CharField(max_length=10)

    unblended_rate = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    unblended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    blended_rate = models.DecimalField(max_digits=17, decimal_places=9,
                                       null=True)

    blended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                       null=True)

    public_on_demand_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                                null=True)

    public_on_demand_rate = models.DecimalField(max_digits=17, decimal_places=9,
                                                null=True)

    tax_type = models.TextField(null=True)

    tags = JSONField(null=True)


class OCPAWSCostLineItemDailySummary(models.Model):
    """A summarized view of OCP on AWS cost."""

    class Meta:
        """Meta for OCPAWSCostLineItemDailySummary."""

        db_table = 'reporting_ocpawscostlineitem_daily_summary'

        indexes = [
            models.Index(
                fields=['usage_start'],
                name='cost_summary_ocp_usage_idx',
            ),
            models.Index(
                fields=['namespace'],
                name='cost_summary_namespace_idx',
            ),
            models.Index(
                fields=['node'],
                name='cost_summary_node_idx',
            ),
            models.Index(
                fields=['resource_id'],
                name='cost_summary_resource_idx',
            ),
            GinIndex(
                fields=['openshift_labels'],
                name='cost_labels_idx',
            ),
        ]

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=False)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateTimeField(null=False)

    usage_end = models.DateTimeField(null=False)

    # Depending on the source this might be pod or volume labels
    openshift_labels = JSONField(null=True)

    # AWS Fields
    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey('AWSAccountAlias',
                                      on_delete=models.PROTECT,
                                      null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    unit = models.CharField(max_length=63, null=True)

    tags = JSONField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9,
                                       null=True)

    normalized_usage_amount = models.FloatField(null=True)

    currency_code = models.CharField(max_length=10, null=True)

    # Cost breakdown can be done by cluster, node, project, and pod.
    # Cluster and node cost can be determined by summing the AWS unblended_cost
    # with a GROUP BY cluster/node.
    # Project cost is a summation of pod_cost with a GROUP BY project
    # The cost of un-utilized resources = sum(unblended_cost) - sum(pod_cost)
    unblended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    pod_cost = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )
