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
"""Populate test data for OCP on Azure reports."""
import pkgutil
import random
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.db import connection
from faker import Faker
from jinjasql import JinjaSql
from model_bakery import baker
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.models import ProviderAuthentication
from api.models import ProviderBillingSource
from api.models import Tenant
from api.provider.models import ProviderInfrastructureMap
from api.report.test.azure.helpers import FakeAzureConfig
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.utils import DateHelper
from reporting.models import AzureCostEntryBill
from reporting.models import OCPAzureCostLineItemDailySummary
from reporting.models import OCPAzureCostLineItemProjectDailySummary


class OCPAzureReportDataGenerator:
    """Populate the database with OCP on Azure report data."""

    def __init__(self, tenant, provider, current_month_only=False, config=None):
        """Set up the class."""
        # prevent future whammy:
        assert isinstance(tenant, Tenant), "not a Tenant type"
        assert isinstance(provider, Provider), "not a Provider type"
        assert isinstance(current_month_only, bool), "not a bool type"
        if config:
            assert isinstance(config, FakeAzureConfig), "not a FakeAzureConfig type"

        self.tenant = tenant
        self.provider = provider
        self.current_month_only = current_month_only
        self.config = config if config else FakeAzureConfig()
        self.fake = Faker()
        self.dh = DateHelper()
        self.provider_uuid = provider.uuid
        self.ocp_generator = None

        # generate a list of dicts with unique keys.
        self.period_ranges, self.report_ranges = self.report_period_and_range()

    def report_period_and_range(self):
        """Return the report period and range."""
        period = []
        ranges = []
        if self.current_month_only:
            report_days = 10
            diff_from_first = self.dh.today - self.dh.this_month_start
            if diff_from_first.days < 10:
                report_days = 1 + diff_from_first.days
                period = [(self.dh.this_month_start, self.dh.this_month_end)]
                ranges = [list(self.dh.this_month_start + relativedelta(days=i) for i in range(report_days))]
            else:
                period = [(self.dh.this_month_start, self.dh.this_month_end)]
                ranges = [list(self.dh.today - relativedelta(days=i) for i in range(report_days))]

        else:
            period = [
                (self.dh.last_month_start, self.dh.last_month_end),
                (self.dh.this_month_start, self.dh.this_month_end),
            ]

            one_month_ago = self.dh.today - relativedelta(months=1)
            diff_from_first = self.dh.today - self.dh.this_month_start
            if diff_from_first.days < 10:
                report_days = 1 + diff_from_first.days
                ranges = [
                    list(self.dh.last_month_start + relativedelta(days=i) for i in range(report_days)),
                    list(self.dh.this_month_start + relativedelta(days=i) for i in range(report_days)),
                ]
            else:
                ranges = [
                    list(one_month_ago - relativedelta(days=i) for i in range(10)),
                    list(self.dh.today - relativedelta(days=i) for i in range(10)),
                ]
        return (period, ranges)

    def remove_data_from_tenant(self):
        """Remove the added data."""
        if self.ocp_generator:
            self.ocp_generator.remove_data_from_tenant()
        with tenant_context(self.tenant):
            for table in (OCPAzureCostLineItemDailySummary, OCPAzureCostLineItemProjectDailySummary):
                table.objects.all().delete()

    def add_ocp_data_to_tenant(self):
        """Populate tenant with OCP data."""
        assert self.cluster_id, "method must be called after add_data_to_tenant"
        self.ocp_generator = OCPReportDataGenerator(self.tenant, self.provider, self.current_month_only)
        ocp_config = {
            "cluster_id": self.cluster_id,
            "cluster_alias": self.cluster_alias,
            "namespaces": self.namespaces,
            "nodes": self.nodes,
        }
        self.ocp_generator.add_data_to_tenant(**ocp_config)

    def add_data_to_tenant(self, fixed_fields=None, service_name=None):
        """Populate tenant with data."""
        words = list({self.fake.word() for _ in range(10)})

        self.cluster_id = random.choice(words)
        self.cluster_alias = random.choice(words)
        self.namespaces = random.sample(words, k=2)
        self.nodes = random.sample(words, k=2)

        self.ocp_azure_summary_line_items = [
            {
                "namespace": random.choice(self.namespaces),
                "pod": random.choice(words),
                "node": node,
                "resource_id": self.fake.ean8(),
            }
            for node in self.nodes
        ]
        with tenant_context(self.tenant):
            for i, period in enumerate(self.period_ranges):
                for report_date in self.report_ranges[i]:
                    for row in self.ocp_azure_summary_line_items:
                        self._randomize_line_item(retained_fields=fixed_fields)
                        if service_name:
                            self.config.service_name = service_name
                        li = self._populate_ocp_azure_cost_line_item_daily_summary(row, report_date)
                        self._populate_ocp_azure_cost_line_item_project_daily_summary(li, row, report_date)
            self._populate_azure_tag_summary()

    def create_ocp_provider(self, cluster_id, cluster_alias, infrastructure_type="Unknown"):
        """Create OCP test provider."""
        auth = baker.make(ProviderAuthentication, provider_resource_name=cluster_id)
        bill = baker.make(ProviderBillingSource, bucket="")
        provider_uuid = uuid4()
        provider_data = {
            "uuid": provider_uuid,
            "name": cluster_alias,
            "authentication": auth,
            "billing_source": bill,
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

    def _randomize_line_item(self, retained_fields=None):
        """Update our FakeAzureConfig to generate a new line item."""
        DEFAULT_FIELDS = ["subscription_guid", "resource_location", "tags"]
        if not retained_fields:
            retained_fields = DEFAULT_FIELDS

        config_dict = {}
        for field in retained_fields:
            if field in self.config:
                config_dict[field] = getattr(self.config, field)
        self.config = FakeAzureConfig(**config_dict)

    def _populate_ocp_azure_cost_line_item_daily_summary(self, row, report_date):
        """Create OCP hourly usage line items."""
        if report_date:
            usage_dt = report_date
        else:
            usage_dt = self.fake.date_time_between_dates(self.dh.this_month_start, self.dh.today)
        usage_qty = random.random() * random.randrange(0, 100)
        pretax = usage_qty * self.config.meter_rate

        data = {
            # OCP Fields:
            "cluster_id": self.cluster_id,
            "cluster_alias": self.cluster_alias,
            "namespace": [row.get("namespace")],
            "pod": [row.get("pod")],
            "node": row.get("node"),
            "resource_id": row.get("resource_id"),
            "usage_start": usage_dt,
            "usage_end": usage_dt,
            # Azure Fields:
            "cost_entry_bill": baker.make(AzureCostEntryBill),
            "subscription_guid": self.config.subscription_guid,
            "instance_type": self.config.instance_type,
            "service_name": self.config.service_name,
            "resource_location": self.config.resource_location,
            "tags": self.select_tags(),
            "usage_quantity": usage_qty,
            "pretax_cost": pretax,
            "markup_cost": pretax * 0.1,
            "offer_id": random.choice([None, self.fake.pyint()]),
            "currency": "USD",
            "unit_of_measure": "some units",
            "shared_projects": 1,
            "project_costs": pretax,
        }

        line_item = OCPAzureCostLineItemDailySummary(**data)
        line_item.save()
        return line_item

    def _populate_ocp_azure_cost_line_item_project_daily_summary(self, li, row, report_date):
        """Create OCP hourly usage line items."""
        data = {
            # OCP Fields:
            "cluster_id": li.cluster_id,
            "cluster_alias": li.cluster_alias,
            "namespace": [row.get("namespace")],
            "pod": [row.get("pod")],
            "node": row.get("node"),
            "resource_id": row.get("resource_id"),
            "usage_start": li.usage_start,
            "usage_end": li.usage_end,
            # Azure Fields:
            "cost_entry_bill": li.cost_entry_bill,
            "subscription_guid": li.subscription_guid,
            "instance_type": li.instance_type,
            "service_name": li.service_name,
            "resource_location": li.resource_location,
            "usage_quantity": li.usage_quantity,
            "unit_of_measure": "some units",
            "offer_id": li.offer_id,
            "currency": "USD",
            "pretax_cost": li.pretax_cost,
            "project_markup_cost": li.markup_cost,
            "pod_cost": random.random() * li.pretax_cost,
        }

        line_item = OCPAzureCostLineItemProjectDailySummary(**data)
        line_item.save()

    def select_tags(self):
        """Return a random selection of the defined tags."""
        return {
            key: self.config.tags[key]
            for key in random.choices(
                list(self.config.tags.keys()), k=random.randrange(2, len(self.config.tags.keys()))
            )
        }

    def _populate_azure_tag_summary(self):
        """Populate the Azure tag summary table."""
        agg_sql = pkgutil.get_data("masu.database", f"sql/reporting_cloudtags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {
            "schema": connection.schema_name,
            "tag_table": "reporting_azuretags_summary",
            "lineitem_table": "reporting_ocpazurecostlineitem_daily_summary",
        }
        agg_sql, agg_sql_params = JinjaSql().prepare_query(agg_sql, agg_sql_params)

        with connection.cursor() as cursor:
            cursor.execute(agg_sql)
