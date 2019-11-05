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
import copy
import random
from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django.db.models import DateTimeField, Max, Sum
from django.db.models.functions import Cast
from tenant_schemas.utils import tenant_context

from api.models import Provider, ProviderAuthentication, ProviderBillingSource
from api.report.test.azure.helpers import AzureReportDataGenerator, FakeAzureConfig
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.utils import DateHelper
from reporting.models import (
    AzureCostEntryBill,
    AzureCostEntryLineItemDaily,
    AzureCostEntryProductService,
    AzureMeter,
)
from reporting.models import (
    OCPAzureCostLineItemDailySummary,
    OCPAzureCostLineItemProjectDailySummary,
)


class OCPAzureReportDataGenerator(OCPReportDataGenerator):
    """Populate the database with OCP on Azure report data."""

    def __init__(self, tenant, provider, current_month_only=False, config=None):
        """Set up the class."""
        super().__init__(tenant, provider, current_month_only=current_month_only)
        self.config = config if config else FakeAzureConfig()


    def remove_data_from_tenant(self):
        """Remove the added data."""
        super().remove_data_from_tenant()
        with tenant_context(self.tenant):
            for table in (AzureCostEntryLineItemDaily,
                          OCPAzureCostLineItemDailySummary,
                          Provider):
                table.objects.all().delete()

    def _populate_azure_tag_summary(self):
        """Populate the AWS tag summary table."""
        raw_sql = """
            INSERT INTO reporting_azuretags_summary
            SELECT l.key,
                array_agg(DISTINCT l.value) as values
            FROM (
                SELECT key,
                    value
                FROM reporting_ocpazurecostlineitem_daily_summary AS li,
                    jsonb_each_text(li.tags) labels
            ) l
            GROUP BY l.key
            ON CONFLICT (key) DO UPDATE
            SET values = EXCLUDED.values
        """

        with connection.cursor() as cursor:
            cursor.execute(raw_sql)