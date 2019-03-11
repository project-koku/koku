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
import random
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import connection
from faker import Faker
from tenant_schemas.utils import tenant_context

from api.report.test.tests_queries import FakeAWSCostData
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummary


class OCPAWSReportDataGenerator:
    """Populate the database with OCP on AWS report data."""

    AWS_SERVICE_CHOICES = ['ec2', 'ebs']

    def __init__(self, tenant):
        """Set up the class."""
        self.tenant = tenant
        self.fake = Faker()
        self.dh = DateHelper()
        self.aws_info = FakeAWSCostData()

        self.today = self.dh.today
        self.one_month_ago = self.today - relativedelta(months=1)

        self.last_month = self.dh.last_month_start

        self.period_ranges = [
            (self.dh.last_month_start, self.dh.last_month_end),
            (self.dh.this_month_start, self.dh.this_month_end),
        ]

        self.report_ranges = [
            (self.one_month_ago - relativedelta(days=i) for i in range(11)),
            (self.today - relativedelta(days=i) for i in range(11)),
        ]

    def add_data_to_tenant(self):
        """Populate tenant with data."""
        self.cluster_id = self.fake.word()
        self.cluster_alias = self.fake.word()
        self.usage_account_id = self.fake.word()
        self.account_alias = self.fake.word()
        self.namespaces = [self.fake.word() for _ in range(2)]
        self.nodes = [self.fake.word() for _ in range(2)]
        self.line_items = [
            {
                'namespace': random.choice(self.namespaces),
                'node': node,
                'pod': self.fake.word(),
                'resource_id': self.fake.word()
            }
            for node in self.nodes
        ]
        with tenant_context(self.tenant):
            for i, period in enumerate(self.period_ranges):
                for report_date in self.report_ranges[i]:
                    self._populate_ocp_aws_cost_line_item_daily_summary(report_date)
            self._populate_aws_tag_summary()

    def remove_data_from_tenant(self):
        """Remove the added data."""
        with tenant_context(self.tenant):
            OCPAWSCostLineItemDailySummary.objects.all().delete()

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
        for row in self.line_items:
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
                    'pod': row.get('pod'),
                    'node': row.get('node'),
                    'resource_id': resource_prefix + row.get('resource_id'),
                    'usage_start': report_date,
                    'usage_end': report_date,
                    'openshift_labels': {},
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
                    'pod_cost': Decimal(random.random()) * unblended_cost
                }
                line_item = OCPAWSCostLineItemDailySummary(**data)
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
