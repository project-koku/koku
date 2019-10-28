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

from django.contrib.postgres.fields import ArrayField, JSONField
from django.contrib.postgres.indexes import GinIndex
from django.db import models


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
                fields=['tags'],
                name='cost_tags_idx',
            ),
            models.Index(
                fields=['product_family'],
                name='ocp_aws_product_family_idx',
            ),
            models.Index(
                fields=['instance_type'],
                name='ocp_aws_instance_type_idx',
            ),
        ]

    # OCP Fields
    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = ArrayField(models.CharField(max_length=253, null=False))

    pod = ArrayField(models.CharField(max_length=253, null=False))

    node = models.CharField(max_length=253, null=False)

    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateTimeField(null=False)

    usage_end = models.DateTimeField(null=False)

    # AWS Fields
    cost_entry_bill = models.ForeignKey('AWSCostEntryBill',
                                        on_delete=models.CASCADE,
                                        null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey('AWSAccountAlias',
                                      on_delete=models.SET_NULL,
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
    # Project cost is a summation of pod costs with a GROUP BY project
    # The cost of un-utilized resources = sum(unblended_cost) - sum(project_cost)
    unblended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    markup_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                      null=True)

    # This is a count of the number of projects that share an AWS resource
    # It is used to divide cost evenly among projects
    shared_projects = models.IntegerField(null=False, default=1)

    # A JSON dictionary of the project cost, keyed by project/namespace name
    # See comment on unblended_cost for project cost explanation
    project_costs = JSONField(null=True)


class OCPAWSCostLineItemProjectDailySummary(models.Model):
    """A summarized view of OCP on AWS cost by OpenShift project."""

    class Meta:
        """Meta for OCPAWSCostLineItemProjectDailySummary."""

        db_table = 'reporting_ocpawscostlineitem_project_daily_summary'

        indexes = [
            models.Index(
                fields=['usage_start'],
                name='cost_proj_sum_ocp_usage_idx',
            ),
            models.Index(
                fields=['namespace'],
                name='cost__proj_sum_namespace_idx',
            ),
            models.Index(
                fields=['node'],
                name='cost_proj_sum_node_idx',
            ),
            models.Index(
                fields=['resource_id'],
                name='cost_proj_sum_resource_idx',
            ),
            GinIndex(
                fields=['pod_labels'],
                name='cost_proj_pod_labels_idx',
            ),
            models.Index(
                fields=['product_family'],
                name='ocp_aws_proj_prod_fam_idx',
            ),
            models.Index(
                fields=['instance_type'],
                name='ocp_aws_proj_inst_type_idx',
            ),
        ]

    # OCP Fields
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

    usage_start = models.DateTimeField(null=False)

    usage_end = models.DateTimeField(null=False)

    # AWS Fields
    cost_entry_bill = models.ForeignKey('AWSCostEntryBill',
                                        on_delete=models.CASCADE,
                                        null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey('AWSAccountAlias',
                                      on_delete=models.SET_NULL,
                                      null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    region = models.CharField(max_length=50, null=True)

    unit = models.CharField(max_length=63, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9,
                                       null=True)

    normalized_usage_amount = models.FloatField(null=True)

    currency_code = models.CharField(max_length=10, null=True)

    unblended_cost = models.DecimalField(max_digits=17, decimal_places=9,
                                         null=True)

    project_markup_cost = models.DecimalField(
        max_digits=17,
        decimal_places=9,
        null=True
    )

    pod_cost = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )
