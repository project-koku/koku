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
"""Test the AWSReportQueryHandler base class."""
import copy
from decimal import Decimal

from api.report.test import FakeAWSCostData
from api.utils import DateHelper
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import connection
from django.db.models import Count
from django.db.models import DateTimeField
from django.db.models import F
from django.db.models import Max
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Cast
from django.db.models.functions import Concat
from masu.processor.tasks import refresh_materialized_views
from reporting.models import AWSAccountAlias
from reporting.models import AWSCostEntry
from reporting.models import AWSCostEntryBill
from reporting.models import AWSCostEntryLineItem
from reporting.models import AWSCostEntryLineItemDaily
from reporting.models import AWSCostEntryLineItemDailySummary
from reporting.models import AWSCostEntryPricing
from reporting.models import AWSCostEntryProduct
from tenant_schemas.utils import tenant_context


class AWSReportDataGenerator:
    """Populate the database with AWS report data."""

    def __init__(self, tenant):
        """Set up the class."""
        self.tenant = tenant
        self.current_month_total = Decimal(0)

    def _populate_daily_table(self):
        included_fields = [
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

    def _populate_daily_summary_table(self):
        included_fields = ["usage_start", "usage_end", "usage_account_id", "availability_zone", "tags"]
        annotations = {
            "product_family": Concat("cost_entry_product__product_family", Value("")),
            "product_code": Concat("cost_entry_product__service_code", Value("")),
            "region": Concat("cost_entry_product__region", Value("")),
            "instance_type": Concat("cost_entry_product__instance_type", Value("")),
            "unit": Concat("cost_entry_pricing__unit", Value("")),
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
            "resource_count": Count("resource_id", distinct=True),
            "resource_ids": ArrayAgg("resource_id", distinct=True),
        }

        entries = AWSCostEntryLineItemDaily.objects.values(*included_fields).annotate(**annotations)
        for entry in entries:
            alias = AWSAccountAlias.objects.filter(account_id=entry["usage_account_id"])
            alias = list(alias).pop() if alias else None
            summary = AWSCostEntryLineItemDailySummary(**entry, account_alias=alias)
            summary.save()
            self.current_month_total += entry["unblended_cost"] + entry["unblended_cost"] * Decimal(0.1)
        AWSCostEntryLineItemDailySummary.objects.update(markup_cost=F("unblended_cost") * 0.1)

    def _populate_tag_summary_table(self):
        """Populate pod label key and values."""
        raw_sql = """
            INSERT INTO reporting_awstags_summary
            SELECT l.key,
                array_agg(DISTINCT l.value) as values
            FROM (
                SELECT key,
                    value
                FROM reporting_awscostentrylineitem_daily AS li,
                    jsonb_each_text(li.tags) labels
            ) l
            GROUP BY l.key
            ON CONFLICT (key) DO UPDATE
            SET values = EXCLUDED.values
        """

        with connection.cursor() as cursor:
            cursor.execute(raw_sql)

    def add_data_to_tenant(self, data, product="ec2"):
        """Populate tenant with data."""
        assert isinstance(data, FakeAWSCostData), "FakeAWSCostData type not provided"

        with tenant_context(self.tenant):
            # get or create alias
            AWSAccountAlias.objects.get_or_create(account_id=data.account_id, account_alias=data.account_alias)

            # create bill
            bill, _ = AWSCostEntryBill.objects.get_or_create(**data.bill)

            # create ec2 product
            product_data = data.product(product)
            ce_product, _ = AWSCostEntryProduct.objects.get_or_create(**product_data)

            # create pricing
            ce_pricing, _ = AWSCostEntryPricing.objects.get_or_create(**data.pricing)

            # add hourly data
            data_start = data.usage_start
            data_end = data.usage_end
            current = data_start

            while current < data_end:
                end_hour = current + DateHelper().one_hour

                # generate copy of data with 1 hour usage range.
                curr_data = copy.deepcopy(data)
                curr_data.usage_end = end_hour
                curr_data.usage_start = current

                # keep line items within the same AZ
                curr_data.availability_zone = data.availability_zone

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

            self._populate_daily_table()
            self._populate_daily_summary_table()
            self._populate_tag_summary_table()
        refresh_materialized_views(self.tenant.schema_name, "AWS")
