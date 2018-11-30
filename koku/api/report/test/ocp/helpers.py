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
"""Test the OCPReportQueryHandler base class."""
import random
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import (DecimalField, ExpressionWrapper, F,
                              Sum)
from faker import Faker
from tenant_schemas.utils import tenant_context

from api.utils import DateHelper
from reporting.models import (OCPUsageLineItem,
                              OCPUsageLineItemAggregates,
                              OCPUsageLineItemDaily,
                              OCPUsageLineItemDailySummary,
                              OCPUsageReport,
                              OCPUsageReportPeriod)


class OCPReportDataGenerator:
    """Populate the database with OCP report data."""

    def __init__(self, tenant):
        """Set up the class."""
        self.tenant = tenant
        self.fake = Faker()
        self.dh = DateHelper()

        self.today = self.dh.today
        self.one_month_ago = self.today - relativedelta(months=1)

        self.last_month = self.dh.last_month_start

        self.period_ranges = [
            (self.dh.last_month_start, self.dh.last_month_end),
            (self.dh.this_month_start, self.dh.this_month_end),
        ]

        if self.one_month_ago.day >= 10:
            self.report_ranges = [
                (self.one_month_ago - relativedelta(days=i) for i in range(11)),
                (self.today - relativedelta(days=i) for i in range(11)),
            ]
        else:
            self.report_ranges = [
                (self.one_month_ago - relativedelta(days=i) for i in range(11)),
                (self.today + relativedelta(days=i) for i in range(11)),
            ]

        self.this_month_filter = {'usage_start__gte': self.dh.this_month_start}
        self.ten_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 10)}
        self.thirty_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 30)}
        self.last_month_filter = {'usage_start__gte': self.dh.last_month_start,
                                  'usage_end__lte': self.dh.last_month_end}

    def add_data_to_tenant(self):
        """Populate tenant with data."""
        self.cluster_id = self.fake.word()
        self.namespaces = [self.fake.word() for _ in range(2)]
        self.nodes = [self.fake.word() for _ in range(2)]
        self.line_items = [
            {
                'namespace': random.choice(self.namespaces),
                'node': node,
                'pod': self.fake.word()
            }
            for node in self.nodes
        ]
        with tenant_context(self.tenant):
            for i, period in enumerate(self.period_ranges):
                report_period = self.create_ocp_report_period(period)

                for report_date in self.report_ranges[i]:
                    report = self.create_ocp_report(
                        report_period,
                        report_date
                    )
                    self.create_line_items(report_period, report)

            self._populate_daily_table()
            self._populate_daily_summary_table()
            self._populate_charge_info()

    def remove_data_from_tenant(self):
        """Remove the added data."""
        with tenant_context(self.tenant):
            for table in (OCPUsageLineItem,
                          OCPUsageLineItemAggregates,
                          OCPUsageLineItemDaily,
                          OCPUsageLineItemDailySummary,
                          OCPUsageReport,
                          OCPUsageReportPeriod):
                table.objects.all().delete()

    def create_ocp_report_period(self, period):
        """Create the OCP report period DB rows."""
        data = {
            'cluster_id': self.cluster_id,
            'report_period_start': period[0],
            'report_period_end': period[1],
            'summary_data_creation_datetime': self.dh._now,
            'summary_data_updated_datetime': self.dh._now,
            'provider_id': 1
        }
        report_period = OCPUsageReportPeriod(**data)
        report_period.save()
        return report_period

    def create_ocp_report(self, period, interval_start):
        """Create the OCP report DB rows."""
        data = {
            'interval_start': interval_start,
            'interval_end': interval_start,
            'report_period': period
        }

        report = OCPUsageReport(**data)
        report.save()
        return report

    def create_line_items(self, report_period, report):
        """Create OCP hourly usage line items."""
        for row in self.line_items:
            data = {
                'report_period': report_period,
                'report': report,
                'namespace': row.get('namespace'),
                'pod': row.get('pod'),
                'node': row.get('node'),
                'pod_usage_cpu_core_seconds': Decimal(random.uniform(0, 3600)),
                'pod_request_cpu_core_seconds': Decimal(random.uniform(0, 3600)),
                'pod_limit_cpu_core_seconds': Decimal(random.uniform(0, 3600)),
                'pod_usage_memory_byte_seconds': Decimal(random.uniform(0, 3600) * 1e9),
                'pod_request_memory_byte_seconds': Decimal(random.uniform(0, 3600) * 1e9),
                'pod_limit_memory_byte_seconds': Decimal(random.uniform(0, 3600) * 1e9),
            }
            line_item = OCPUsageLineItem(**data)
            line_item.save()

    def _populate_daily_table(self):
        """Populate the daily table."""
        included_fields = [
            'namespace',
            'pod',
            'node',
        ]
        annotations = {
            'usage_start': F('report__interval_start'),
            'usage_end': F('report__interval_start'),
            'pod_usage_cpu_core_seconds': Sum('pod_usage_cpu_core_seconds'),
            'pod_request_cpu_core_seconds': Sum('pod_request_cpu_core_seconds'),
            'pod_limit_cpu_core_seconds': Sum('pod_limit_cpu_core_seconds'),
            'pod_usage_memory_byte_seconds': Sum('pod_usage_memory_byte_seconds'),
            'pod_request_memory_byte_seconds': Sum('pod_request_memory_byte_seconds'),
            'pod_limit_memory_byte_seconds': Sum('pod_limit_memory_byte_seconds'),
            'cluster_id': F('report_period__cluster_id')
        }
        entries = OCPUsageLineItem.objects\
            .values(*included_fields)\
            .annotate(**annotations)
        for entry in entries:
            entry['total_seconds'] = 3600
            daily = OCPUsageLineItemDaily(**entry)
            daily.save()

    def _populate_daily_summary_table(self):
        """Populate the daily summary table."""
        included_fields = [
            'usage_start',
            'usage_end',
            'namespace',
            'pod',
            'node',
            'cluster_id'
        ]
        annotations = {
            'pod_usage_cpu_core_hours': Sum(
                ExpressionWrapper(
                    F('pod_usage_cpu_core_seconds') / 3600,
                    output_field=DecimalField()
                )
            ),
            'pod_request_cpu_core_hours': Sum(
                ExpressionWrapper(
                    F('pod_request_cpu_core_seconds') / 3600,
                    output_field=DecimalField()
                )
            ),
            'pod_limit_cpu_core_hours': Sum(
                ExpressionWrapper(
                    F('pod_limit_cpu_core_seconds') / 3600,
                    output_field=DecimalField()
                )
            ),
            'pod_usage_memory_gigabytes': Sum(
                ExpressionWrapper(
                    F('pod_usage_memory_byte_seconds') / F('total_seconds'),
                    output_field=DecimalField()
                )
            ) * 1e-9,
            'pod_request_memory_gigabytes': Sum(
                ExpressionWrapper(
                    F('pod_request_memory_byte_seconds') / F('total_seconds'),
                    output_field=DecimalField()
                )
            ) * 1e-9,
            'pod_limit_memory_gigabytes': ExpressionWrapper(
                F('pod_limit_memory_byte_seconds') / F('total_seconds'),
                output_field=DecimalField()
            ) * 1e-9,
        }

        entries = OCPUsageLineItemDaily.objects.values(*included_fields).annotate(**annotations)
        for entry in entries:
            summary = OCPUsageLineItemDailySummary(**entry)
            summary.save()

    def _populate_charge_info(self):
        """Populate the charge information in summary table."""
        entries = OCPUsageLineItemDailySummary.objects.all()
        for entry in entries:
            mem_usage = entry.pod_usage_memory_gigabytes
            mem_request = entry.pod_request_memory_gigabytes
            mem_charge = max(float(mem_usage), float(mem_request)) * 0.25

            entry.pod_charge_memory_gigabyte_hours = mem_charge

            cpu_usage = entry.pod_usage_cpu_core_hours
            cpu_request = entry.pod_request_cpu_core_hours
            cpu_charge = max(float(cpu_usage), float(cpu_request)) * 0.50

            entry.pod_charge_cpu_core_hours = cpu_charge

            entry.save()
