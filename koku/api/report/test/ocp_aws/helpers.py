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
import random
from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django.db.models import DateTimeField, Max, Sum
from django.db.models.functions import Cast
from tenant_schemas.utils import tenant_context

from api.models import Provider, ProviderAuthentication, ProviderBillingSource
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.report.test.tests_queries import FakeAWSCostData
from api.utils import DateHelper
from reporting.models import (AWSAccountAlias,
                              AWSCostEntry,
                              AWSCostEntryBill,
                              AWSCostEntryLineItem,
                              AWSCostEntryLineItemDaily,
                              AWSCostEntryPricing,
                              AWSCostEntryProduct)
from reporting.models import (OCPAWSCostLineItemDailySummary,
                              OCPAWSCostLineItemProjectDailySummary)


class OCPAWSReportDataGenerator(OCPReportDataGenerator):
    """Populate the database with OCP on AWS report data."""

    AWS_SERVICE_CHOICES = ['ec2', 'ebs']

    def __init__(self, tenant, current_month_only=False):
        """Set up the class."""
        super().__init__(tenant, current_month_only)

        aws_usage_start = min(self.report_ranges[0])
        aws_usage_end = max(self.report_ranges[0])

        self.aws_info = FakeAWSCostData(usage_start=aws_usage_start,
                                        usage_end=aws_usage_end,
                                        resource_id=self.resource_id)

    def create_ocp_provider(self, cluster_id, cluster_alias):
        """Create OCP test provider."""
        authentication_data = {
            'uuid': uuid4(),
            'provider_resource_name': cluster_id,
        }
        authentication_id = ProviderAuthentication(**authentication_data)
        authentication_id.save()

        billing_source_data = {
            'uuid': uuid4(),
            'bucket': '',
        }
        billing_source_id = ProviderBillingSource(**billing_source_data)
        billing_source_id.save()

        provider_uuid = uuid4()
        provider_data = {
            'uuid': provider_uuid,
            'name': cluster_alias,
            'authentication': authentication_id,
            'billing_source': billing_source_id,
            'customer': None,
            'created_by': None,
            'type': 'OCP',
            'setup_complete': False
        }
        provider_id = Provider(**provider_data)
        provider_id.save()
        self.cluster_alias = cluster_alias
        self.provider_uuid = provider_uuid
        return provider_id

    def add_data_to_tenant(self, **kwargs):
        """Populate tenant with data."""
        super().add_data_to_tenant(**kwargs)
        self.usage_account_id = self.fake.word()
        self.account_alias = self.fake.word()

        self.ocp_aws_summary_line_items = [
            {
                'namespace': random.choice(self.namespaces),
                'node': node,
                'pod': self.fake.word(),
                'resource_id': self.resource_id
            }
            for node in self.nodes
        ]
        with tenant_context(self.tenant):
            for i, period in enumerate(self.period_ranges):
                for report_date in self.report_ranges[i]:
                    self._populate_ocp_aws_cost_line_item_daily_summary(report_date)
                    self._populate_ocp_aws_cost_line_item_project_daily_summary(report_date)
            self._populate_aws_tag_summary()

    def add_aws_data_to_tenant(self, product='ec2'):
        """Populate tenant with AWS data."""
        with tenant_context(self.tenant):
            # get or create alias
            AWSAccountAlias.objects.get_or_create(
                account_id=self.aws_info.account_id,
                account_alias=self.aws_info.account_alias)

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
                cost_entry_data.update({'bill': bill})
                cost_entry, _ = AWSCostEntry.objects.get_or_create(**cost_entry_data)

                # create line item
                line_item_data = curr_data.line_item(product)
                model_instances = {'cost_entry': cost_entry,
                                   'cost_entry_bill': bill,
                                   'cost_entry_product': ce_product,
                                   'cost_entry_pricing': ce_pricing}
                line_item_data.update(model_instances)

                line_item, _ = AWSCostEntryLineItem.objects.get_or_create(**line_item_data)

                current = end_hour

            self._populate_aws_daily_table()

    def _populate_aws_daily_table(self):
        included_fields = [
            'cost_entry_product_id',
            'cost_entry_pricing_id',
            'cost_entry_reservation_id',
            'line_item_type',
            'usage_account_id',
            'usage_type',
            'operation',
            'availability_zone',
            'resource_id',
            'tax_type',
            'product_code',
            'tags'
        ]
        annotations = {
            'usage_start': Cast('usage_start', DateTimeField()),
            'usage_end': Cast('usage_start', DateTimeField()),
            'usage_amount': Sum('usage_amount'),
            'normalization_factor': Max('normalization_factor'),
            'normalized_usage_amount': Sum('normalized_usage_amount'),
            'currency_code': Max('currency_code'),
            'unblended_rate': Max('unblended_rate'),
            'unblended_cost': Sum('unblended_cost'),
            'blended_rate': Max('blended_rate'),
            'blended_cost': Sum('blended_cost'),
            'public_on_demand_cost': Sum('public_on_demand_cost'),
            'public_on_demand_rate': Max('public_on_demand_rate')
        }

        entries = AWSCostEntryLineItem.objects\
            .values(*included_fields)\
            .annotate(**annotations)
        for entry in entries:
            daily = AWSCostEntryLineItemDaily(**entry)
            daily.save()

    def remove_data_from_tenant(self):
        """Remove the added data."""
        super().remove_data_from_tenant()
        with tenant_context(self.tenant):
            for table in (AWSAccountAlias,
                          AWSCostEntryLineItemDaily,
                          AWSCostEntryLineItem,
                          OCPAWSCostLineItemDailySummary,
                          Provider):
                table.objects.all().delete()

    def _get_tags(self):
        """Create tags for output data."""
        apps = [self.fake.word(), self.fake.word(), self.fake.word(),  # pylint: disable=no-member
                self.fake.word(), self.fake.word(), self.fake.word()]  # pylint: disable=no-member
        organizations = [self.fake.word(), self.fake.word(),  # pylint: disable=no-member
                         self.fake.word(), self.fake.word()]  # pylint: disable=no-member
        markets = [self.fake.word(), self.fake.word(), self.fake.word(),  # pylint: disable=no-member
                   self.fake.word(), self.fake.word(), self.fake.word()]  # pylint: disable=no-member
        versions = [self.fake.word(), self.fake.word(), self.fake.word(),  # pylint: disable=no-member
                    self.fake.word(), self.fake.word(), self.fake.word()]  # pylint: disable=no-member

        seeded_labels = {'environment': ['dev', 'ci', 'qa', 'stage', 'prod'],
                         'app': apps,
                         'organization': organizations,
                         'market': markets,
                         'version': versions
                         }
        gen_label_keys = [self.fake.word(), self.fake.word(), self.fake.word(),  # pylint: disable=no-member
                          self.fake.word(), self.fake.word(), self.fake.word()]  # pylint: disable=no-member
        all_label_keys = list(seeded_labels.keys()) + gen_label_keys
        num_labels = random.randint(2, len(all_label_keys))
        chosen_label_keys = random.choices(all_label_keys, k=num_labels)

        labels = {}
        for label_key in chosen_label_keys:
            label_value = self.fake.word()  # pylint: disable=no-member
            if label_key in seeded_labels:
                label_value = random.choice(seeded_labels[label_key])

            labels['{}_label'.format(label_key)] = label_value

        return labels

    def _populate_ocp_aws_cost_line_item_daily_summary(self, report_date):
        """Create OCP hourly usage line items."""
        for row in self.ocp_aws_summary_line_items:
            for aws_service in self.AWS_SERVICE_CHOICES:
                resource_prefix = 'i-'
                unit = 'Hrs'
                instance_type = random.choice(self.aws_info.SOME_INSTANCE_TYPES)
                if aws_service == 'ebs':
                    resource_prefix = 'vol-'
                    unit = 'GB-Mo'
                    instance_type = None
                aws_product = self.aws_info._products.get(aws_service)
                region = random.choice(self.aws_info.SOME_REGIONS)
                az = region + random.choice(['a', 'b', 'c'])
                usage_amount = Decimal(random.uniform(0, 100))
                unblended_cost = Decimal(random.uniform(0, 10)) * usage_amount

                data = {
                    'cluster_id': self.cluster_id,
                    'cluster_alias': self.cluster_alias,
                    'namespace': [row.get('namespace')],
                    'pod': [row.get('pod')],
                    'node': row.get('node'),
                    'resource_id': resource_prefix + row.get('resource_id'),
                    'usage_start': report_date,
                    'usage_end': report_date,
                    'product_code': aws_product.get('service_code'),
                    'product_family': aws_product.get('product_family'),
                    'instance_type': instance_type,
                    'usage_account_id': self.usage_account_id,
                    'account_alias': None,
                    'availability_zone': az,
                    'region': region,
                    'unit': unit,
                    'tags': self._get_tags(),
                    'usage_amount': usage_amount,
                    'normalized_usage_amount': usage_amount,
                    'unblended_cost': unblended_cost,
                    'project_costs': {row.get('namespace'): float(Decimal(random.random()) * unblended_cost)}
                }
                line_item = OCPAWSCostLineItemDailySummary(**data)
                line_item.save()

    def _populate_ocp_aws_cost_line_item_project_daily_summary(self, report_date):
        """Create OCP hourly usage line items."""
        for row in self.ocp_aws_summary_line_items:
            for aws_service in self.AWS_SERVICE_CHOICES:
                resource_prefix = 'i-'
                unit = 'Hrs'
                instance_type = random.choice(self.aws_info.SOME_INSTANCE_TYPES)
                if aws_service == 'ebs':
                    resource_prefix = 'vol-'
                    unit = 'GB-Mo'
                    instance_type = None
                aws_product = self.aws_info._products.get(aws_service)
                region = random.choice(self.aws_info.SOME_REGIONS)
                az = region + random.choice(['a', 'b', 'c'])
                usage_amount = Decimal(random.uniform(0, 100))
                unblended_cost = Decimal(random.uniform(0, 10)) * usage_amount

                data = {
                    'cluster_id': self.cluster_id,
                    'cluster_alias': self.cluster_alias,
                    'namespace': row.get('namespace'),
                    'node': row.get('node'),
                    'resource_id': resource_prefix + row.get('resource_id'),
                    'usage_start': report_date,
                    'usage_end': report_date,
                    'product_code': aws_product.get('service_code'),
                    'product_family': aws_product.get('product_family'),
                    'instance_type': instance_type,
                    'usage_account_id': self.usage_account_id,
                    'account_alias': None,
                    'availability_zone': az,
                    'region': region,
                    'unit': unit,
                    'tags': self._get_tags(),
                    'usage_amount': usage_amount,
                    'normalized_usage_amount': usage_amount,
                    'project_cost': Decimal(random.random()) * unblended_cost
                }
                line_item = OCPAWSCostLineItemProjectDailySummary(**data)
                line_item.save()

    def _populate_aws_tag_summary(self):
        """Populate the AWS tag summary table."""
        raw_sql = """
            INSERT INTO reporting_awstags_summary
            SELECT l.key,
                array_agg(DISTINCT l.value) as values
            FROM (
                SELECT key,
                    value
                FROM reporting_ocpawscostlineitem_daily_summary AS li,
                    jsonb_each_text(li.tags) labels
            ) l
            GROUP BY l.key
            ON CONFLICT (key) DO UPDATE
            SET values = EXCLUDED.values
        """

        with connection.cursor() as cursor:
            cursor.execute(raw_sql)
