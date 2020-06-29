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
"""Populate test data for OCP on AWS reports."""
import copy
import pkgutil
import random
from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django.db.models import DateTimeField
from django.db.models import Max
from django.db.models import Sum
from django.db.models.functions import Cast
from jinjasql import JinjaSql
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.models import ProviderAuthentication
from api.models import ProviderBillingSource
from api.provider.models import ProviderInfrastructureMap
from api.report.test import FakeAWSCostData
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.utils import DateHelper
from reporting.models import AWSAccountAlias
from reporting.models import AWSCostEntry
from reporting.models import AWSCostEntryBill
from reporting.models import AWSCostEntryLineItem
from reporting.models import AWSCostEntryLineItemDaily
from reporting.models import AWSCostEntryPricing
from reporting.models import AWSCostEntryProduct
from reporting.models import OCPAWSCostLineItemDailySummary
from reporting.models import OCPAWSCostLineItemProjectDailySummary


class OCPAWSReportDataGenerator(OCPReportDataGenerator):
    """Populate the database with OCP on AWS report data."""

    AWS_SERVICE_CHOICES = ["ec2", "ebs"]

    def __init__(self, tenant, provider, current_month_only=False):
        """Set up the class."""
        super().__init__(tenant, provider, current_month_only)

        aws_usage_start = min(self.report_ranges[0])
        aws_usage_end = max(self.report_ranges[0])

        self.aws_info = FakeAWSCostData(
            self.provider, usage_start=aws_usage_start, usage_end=aws_usage_end, resource_id=self.resource_id
        )
        self._tags = self._generate_tags()

    @property
    def tags(self):
        """Tags property."""
        if not self._tags:
            self._tags = self._generate_tags()
        return self._tags

    def create_ocp_provider(self, cluster_id, cluster_alias, infrastructure_type="Unknown"):
        """Create OCP test provider."""
        authentication_data = {"uuid": uuid4(), "provider_resource_name": cluster_id}
        authentication_id = ProviderAuthentication(**authentication_data)
        authentication_id.save()

        billing_source_data = {"uuid": uuid4(), "bucket": ""}
        billing_source_id = ProviderBillingSource(**billing_source_data)
        billing_source_id.save()

        provider_uuid = uuid4()
        provider_data = {
            "uuid": provider_uuid,
            "name": cluster_alias,
            "authentication": authentication_id,
            "billing_source": billing_source_id,
            "customer": None,
            "created_by": None,
            "type": Provider.PROVIDER_OCP,
            "setup_complete": False,
            "infrastructure": None,
        }
        provider = Provider(**provider_data)
        infrastructure = ProviderInfrastructureMap(
            infrastructure_provider=provider, infrastructure_type=infrastructure_type
        )
        infrastructure.save()
        provider.infrastructure = infrastructure
        provider.save()
        self.cluster_alias = cluster_alias
        self.provider_uuid = provider_uuid
        return provider

    def add_data_to_tenant(self, **kwargs):
        """Populate tenant with data."""
        super().add_data_to_tenant(**kwargs)
        self.usage_account_id = self.fake.word()
        self.account_alias = self.fake.word()

        self.ocp_aws_summary_line_items = [
            {
                "namespace": random.choice(self.namespaces),
                "node": node,
                "pod": self.fake.word(),
                "resource_id": self.resource_id,
            }
            for node in self.nodes
        ]
        with tenant_context(self.tenant):
            for i, period in enumerate(self.period_ranges):
                for report_date in self.report_ranges[i]:
                    self._populate_ocp_aws_cost_line_item_daily_summary(report_date)
                    self._populate_ocp_aws_cost_line_item_project_daily_summary(report_date)
            self._populate_ocpaws_tag_summary()

    def add_aws_data_to_tenant(self, product="ec2"):
        """Populate tenant with AWS data."""
        with tenant_context(self.tenant):
            # get or create alias
            AWSAccountAlias.objects.get_or_create(
                account_id=self.aws_info.account_id, account_alias=self.aws_info.account_alias
            )

            # create bill
            bill, _ = AWSCostEntryBill.objects.get_or_create(**self.aws_info.bill)

            # create ec2 product
            product_data = self.aws_info.product(product)
            ce_product, _ = AWSCostEntryProduct.objects.get_or_create(**product_data)

            # create pricing
            ce_pricing, _ = AWSCostEntryPricing.objects.get_or_create(**self.aws_info.pricing)

            # add hourly data
            data_start = self.aws_info.usage_start
            data_end = self.aws_info.usage_end
            current = data_start

            while current < data_end:
                end_hour = current + DateHelper().one_hour

                # generate copy of data with 1 hour usage range.
                curr_data = copy.deepcopy(self.aws_info)
                curr_data.usage_end = end_hour
                curr_data.usage_start = current

                # keep line items within the same AZ
                curr_data.availability_zone = self.aws_info.availability_zone

                # get or create cost entry
                cost_entry_data = curr_data.cost_entry
                cost_entry_data.update({"bill": bill})
                cost_entry, _ = AWSCostEntry.objects.get_or_create(**cost_entry_data)

                # create line item
                line_item_data = curr_data.line_item(product)
                model_instances = {
                    "cost_entry": cost_entry,
                    "cost_entry_bill": bill,
                    "cost_entry_product": ce_product,
                    "cost_entry_pricing": ce_pricing,
                }
                line_item_data.update(model_instances)

                line_item, _ = AWSCostEntryLineItem.objects.get_or_create(**line_item_data)

                current = end_hour

            self._populate_aws_daily_table()

    def _populate_aws_daily_table(self):
        included_fields = [
            "cost_entry_bill_id",
            "cost_entry_product_id",
            "cost_entry_pricing_id",
            "cost_entry_reservation_id",
            "line_item_type",
            "usage_account_id",
            "usage_type",
            "operation",
            "availability_zone",
            "resource_id",
            "tax_type",
            "product_code",
            "tags",
        ]
        annotations = {
            "usage_start": Cast("usage_start", DateTimeField()),
            "usage_end": Cast("usage_start", DateTimeField()),
            "usage_amount": Sum("usage_amount"),
            "normalization_factor": Max("normalization_factor"),
            "normalized_usage_amount": Sum("normalized_usage_amount"),
            "currency_code": Max("currency_code"),
            "unblended_rate": Max("unblended_rate"),
            "unblended_cost": Sum("unblended_cost"),
            "blended_rate": Max("blended_rate"),
            "blended_cost": Sum("blended_cost"),
            "public_on_demand_cost": Sum("public_on_demand_cost"),
            "public_on_demand_rate": Max("public_on_demand_rate"),
        }

        entries = AWSCostEntryLineItem.objects.values(*included_fields).annotate(**annotations)
        for entry in entries:
            daily = AWSCostEntryLineItemDaily(**entry)
            daily.save()

    def remove_data_from_tenant(self):
        """Remove the added data."""
        super().remove_data_from_tenant()
        with tenant_context(self.tenant):
            for table in (
                AWSAccountAlias,
                AWSCostEntryLineItemDaily,
                AWSCostEntryLineItem,
                OCPAWSCostLineItemDailySummary,
                Provider,
            ):
                table.objects.all().delete()

    def _generate_tags(self):
        """Create tags for output data."""
        apps = [
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
        ]
        organizations = [self.fake.word(), self.fake.word(), self.fake.word(), self.fake.word()]
        markets = [
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
        ]
        versions = [
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
        ]

        seeded_labels = {
            "environment": ["dev", "ci", "qa", "stage", "prod"],
            "app": apps,
            "organization": organizations,
            "market": markets,
            "version": versions,
        }
        gen_label_keys = [
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
            self.fake.word(),
        ]
        all_label_keys = list(seeded_labels.keys()) + gen_label_keys
        num_labels = random.randint(2, len(all_label_keys))
        chosen_label_keys = random.choices(all_label_keys, k=num_labels)

        labels = {}
        for label_key in chosen_label_keys:
            label_value = self.fake.word()
            if label_key in seeded_labels:
                label_value = random.choice(seeded_labels[label_key])

            labels[f"{label_key}_label"] = label_value

        return labels

    def _populate_ocp_aws_cost_line_item_daily_summary(self, report_date):
        """Create OCP hourly usage line items."""
        for row in self.ocp_aws_summary_line_items:
            for aws_service in self.AWS_SERVICE_CHOICES:
                resource_prefix = "i-"
                unit = "Hrs"
                instance_type = random.choice(self.aws_info.SOME_INSTANCE_TYPES)
                if aws_service == "ebs":
                    resource_prefix = "vol-"
                    unit = "GB-Mo"
                    instance_type = None
                aws_product = self.aws_info._products.get(aws_service)
                region = random.choice(self.aws_info.SOME_REGIONS)
                az = region + random.choice(["a", "b", "c"])
                usage_amount = Decimal(random.uniform(0, 100))
                unblended_cost = Decimal(random.uniform(0, 10)) * usage_amount
                project_costs = {row.get("namespace"): float(Decimal(random.random()) * unblended_cost)}
                bill, _ = AWSCostEntryBill.objects.get_or_create(**self.aws_info.bill)

                data = {
                    "cost_entry_bill_id": bill.id,
                    "cluster_id": self.cluster_id,
                    "cluster_alias": self.cluster_alias,
                    "namespace": [row.get("namespace")],
                    "pod": [row.get("pod")],
                    "node": row.get("node"),
                    "resource_id": resource_prefix + row.get("resource_id"),
                    "usage_start": report_date,
                    "usage_end": report_date,
                    "product_code": aws_product.get("service_code"),
                    "product_family": aws_product.get("product_family"),
                    "instance_type": instance_type,
                    "usage_account_id": self.usage_account_id,
                    "account_alias": None,
                    "availability_zone": az,
                    "region": region,
                    "tags": self.tags,
                    "unit": unit,
                    "usage_amount": usage_amount,
                    "normalized_usage_amount": usage_amount,
                    "unblended_cost": unblended_cost,
                    "markup_cost": unblended_cost * Decimal(0.1),
                    "project_costs": project_costs,
                }
                line_item = OCPAWSCostLineItemDailySummary(**data)
                line_item.save()

    def _populate_ocp_aws_cost_line_item_project_daily_summary(self, report_date):
        """Create OCP hourly usage line items."""
        for row in self.ocp_aws_summary_line_items:
            for aws_service in self.AWS_SERVICE_CHOICES:
                resource_prefix = "i-"
                unit = "Hrs"
                instance_type = random.choice(self.aws_info.SOME_INSTANCE_TYPES)
                if aws_service == "ebs":
                    resource_prefix = "vol-"
                    unit = "GB-Mo"
                    instance_type = None
                aws_product = self.aws_info._products.get(aws_service)
                region = random.choice(self.aws_info.SOME_REGIONS)
                az = region + random.choice(["a", "b", "c"])
                usage_amount = Decimal(random.uniform(0, 100))
                unblended_cost = Decimal(random.uniform(0, 10)) * usage_amount

                data = {
                    "cluster_id": self.cluster_id,
                    "cluster_alias": self.cluster_alias,
                    "namespace": row.get("namespace"),
                    "node": row.get("node"),
                    "pod": row.get("pod"),
                    "pod_labels": self.tags,
                    "resource_id": resource_prefix + row.get("resource_id"),
                    "usage_start": report_date,
                    "usage_end": report_date,
                    "product_code": aws_product.get("service_code"),
                    "product_family": aws_product.get("product_family"),
                    "instance_type": instance_type,
                    "usage_account_id": self.usage_account_id,
                    "account_alias": None,
                    "availability_zone": az,
                    "region": region,
                    "unit": unit,
                    "usage_amount": usage_amount,
                    "normalized_usage_amount": usage_amount,
                    "pod_cost": Decimal(random.random()) * unblended_cost,
                }
                line_item = OCPAWSCostLineItemProjectDailySummary(**data)
                line_item.save()

    def _populate_ocpaws_tag_summary(self):
        """Populate the AWS tag summary table."""
        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpawstags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": connection.schema_name}
        agg_sql, agg_sql_params = JinjaSql().prepare_query(agg_sql, agg_sql_params)

        with connection.cursor() as cursor:
            cursor.execute(agg_sql)
