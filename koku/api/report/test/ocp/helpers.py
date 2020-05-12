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
import hashlib
import math
import pkgutil
import random
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Max
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce
from faker import Faker
from jinjasql import JinjaSql
from tenant_schemas.utils import tenant_context

from api.utils import DateHelper
from reporting.models import CostSummary
from reporting.models import OCPNodeLabelLineItem
from reporting.models import OCPNodeLabelLineItemDaily
from reporting.models import OCPStorageLineItem
from reporting.models import OCPStorageLineItemDaily
from reporting.models import OCPUsageLineItem
from reporting.models import OCPUsageLineItemDaily
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import OCPUsageReport
from reporting.models import OCPUsageReportPeriod
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class OCPReportDataGenerator:
    """Populate the database with OCP report data."""

    def __init__(self, tenant, provider, current_month_only=False, dated_tags=None):
        """Set up the class."""
        self.tenant = tenant
        self.provider = provider
        self.fake = Faker()
        self.dh = DateHelper()
        self.labels = []

        self.dated_tags = True if dated_tags is None or dated_tags is True else False

        self.today = self.dh.today
        self.one_month_ago = self.today - relativedelta(months=1)

        self.last_month = self.dh.last_month_start
        self.resource_id = self.fake.ean8()

        if current_month_only:
            report_days = 10
            first_of_month = self.today.replace(microsecond=0, second=0, minute=0, day=1)
            diff_from_first = self.today - first_of_month
            if diff_from_first.days < 10:
                report_days = 1 + diff_from_first.days
            self.period_ranges = [(self.dh.this_month_start, self.dh.this_month_end)]
            self.report_ranges = [list(self.today - relativedelta(days=i) for i in range(report_days))]

        else:
            self.period_ranges = [
                (self.dh.last_month_start, self.dh.last_month_end),
                (self.dh.this_month_start, self.dh.this_month_end),
            ]

            self.report_ranges = [
                list(self.one_month_ago - relativedelta(days=i) for i in range(10)),
                list(self.today - relativedelta(days=i) for i in range(10)),
            ]

    def create_manifest_entry(self, billing_period_start, provider_uuid):
        """Populate a report manifest entry."""
        manifest_creation_datetime = billing_period_start + relativedelta(days=random.randint(1, 27))
        manifest_updated_datetime = manifest_creation_datetime + relativedelta(days=random.randint(1, 2))
        data = {
            "assembly_id": uuid4(),
            "manifest_creation_datetime": manifest_creation_datetime,
            "manifest_updated_datetime": manifest_updated_datetime,
            "billing_period_start_datetime": billing_period_start,
            "num_processed_files": 1,
            "num_total_files": 1,
            "provider_id": provider_uuid,
        }
        manifest_entry = CostUsageReportManifest(**data)
        manifest_entry.save()
        return manifest_entry

    def set_manifest_completed(self, manifest):
        """Update the manifest_completed_datetime column."""
        manifest.manifest_completed_datetime = self.dh.now
        manifest.save()

    def create_report_status_entry(self, billing_period_start, manifest_id):
        """Populate a report status entry."""
        etag_hasher = hashlib.new("ripemd160")
        etag_hasher.update(bytes(str(billing_period_start), "utf-8"))
        ocp_etag = etag_hasher.hexdigest()

        last_started_datetime = billing_period_start + relativedelta(days=random.randint(1, 3))
        last_completed_datetime = last_started_datetime + relativedelta(days=1)
        data = {
            "report_name": uuid4(),
            "last_completed_datetime": last_completed_datetime,
            "last_started_datetime": last_started_datetime,
            "etag": ocp_etag,
            "manifest_id": manifest_id,
        }
        status_entry = CostUsageReportStatus(**data)
        status_entry.save()
        return status_entry

    def add_data_to_tenant(self, **kwargs):
        """Populate tenant with data."""
        words = list({self.fake.word() for _ in range(10)})
        provider_uuid = kwargs.get("provider_uuid", self.provider.uuid)

        self.cluster_id = kwargs.get("cluster_id", random.choice(words))
        self.cluster_alias = kwargs.get("cluster_alias", random.choice(words))
        self.namespaces = kwargs.get("namespaces", random.sample(words, k=2))
        self.nodes = kwargs.get("nodes", random.sample(words, k=2))

        self.pods = random.sample(words, k=2)
        self.storage_classes = ["gp2", "standard", "magnetic"]
        self.line_items = [
            {
                "namespace": self.namespaces[i],
                "node": node,
                "pod": self.pods[i],
                "persistentvolumeclaim": self.pods[i] + "_volume_claim",
                "persistentvolume": self.pods[i] + "_volume",
                "storageclass": random.choice(self.storage_classes),
            }
            for i, node in enumerate(self.nodes)
        ]
        self.node_cost = kwargs.get("node_cost", random.randint(1, 200))

        with tenant_context(self.tenant):
            for i, period in enumerate(self.period_ranges):
                report_period = self.create_ocp_report_period(period, provider_uuid)
                manifest_entry = self.create_manifest_entry(report_period.report_period_start, provider_uuid)
                self.create_report_status_entry(manifest_entry.billing_period_start_datetime, manifest_entry.id)
                for report_date in self.report_ranges[i]:
                    report = self.create_ocp_report(report_period, report_date)
                    self.create_line_items(report_period, report, self.resource_id)
                    self.create_storage_line_items(report_period, report)
                    self.create_node_label_line_items(report_period, report)
                self.set_manifest_completed(manifest_entry)

            self._populate_node_label_daily_table()
            self._populate_daily_table()
            self._populate_daily_summary_table()
            self._populate_storage_daily_table()
            self._populate_storage_daily_summary_table()
            self._populate_charge_info()
            self._populate_storage_charge_info()
            self._populate_pod_label_summary_table()
            self._populate_volume_label_summary_table()
            self._populate_cost_summary_table()

            for period in self.period_ranges:
                self._populate_monthly_charge_info(period[0], self.node_cost, len(self.nodes))

    def remove_data_from_tenant(self):
        """Remove the added data."""
        with tenant_context(self.tenant):
            for table in (
                OCPUsageLineItem,
                OCPUsageLineItemDaily,
                OCPUsageLineItemDailySummary,
                OCPStorageLineItem,
                OCPStorageLineItemDaily,
                OCPNodeLabelLineItem,
                OCPNodeLabelLineItemDaily,
                OCPUsageReport,
                OCPUsageReportPeriod,
            ):
                table.objects.all().delete()

    def remove_data_from_reporting_common(self):
        """Remove the public report statistics."""
        for table in (CostUsageReportManifest, CostUsageReportStatus):
            table.objects.all().delete()

    def create_ocp_report_period(self, period, provider_uuid):
        """Create the OCP report period DB rows."""
        data = {
            "cluster_id": self.cluster_id,
            "report_period_start": period[0],
            "report_period_end": period[1],
            "summary_data_creation_datetime": self.dh._now,
            "summary_data_updated_datetime": self.dh._now,
            "derived_cost_datetime": self.dh._now,
            "provider_id": provider_uuid,
        }
        report_period, _ = OCPUsageReportPeriod.objects.get_or_create(**data)
        # report_period.save()
        return report_period

    def create_ocp_report(self, period, interval_start):
        """Create the OCP report DB rows."""
        data = {"interval_start": interval_start, "interval_end": interval_start, "report_period": period}

        report = OCPUsageReport(**data)
        report.save()
        return report

    def _gen_openshift_labels(self, report):
        """Create pod labels for output data."""
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
            if self.dated_tags:
                labels[
                    "{}-{}-{}*{}_label".format(
                        report.interval_start.month, report.interval_start.day, report.interval_start.year, label_key
                    )
                ] = label_value
            else:
                labels[f"{label_key}_label"] = label_value

        self.labels.append((report, labels))
        return labels

    def create_line_items(self, report_period, report, resource_id):
        """Create OCP hourly usage line items."""
        node_cpu_cores = random.randint(1, 8)
        node_memory_gb = random.randint(4, 32)
        for row in self.line_items:
            data = {
                "report_period": report_period,
                "report": report,
                "namespace": row.get("namespace"),
                "pod": row.get("pod"),
                "node": row.get("node"),
                "pod_usage_cpu_core_seconds": Decimal(random.uniform(0, 3600)),
                "pod_request_cpu_core_seconds": Decimal(random.uniform(0, 3600)),
                "pod_limit_cpu_core_seconds": Decimal(random.uniform(0, 3600)),
                "pod_usage_memory_byte_seconds": Decimal(random.uniform(0, 3600) * 1e9),
                "pod_request_memory_byte_seconds": Decimal(random.uniform(0, 3600) * 1e9),
                "pod_limit_memory_byte_seconds": Decimal(random.uniform(0, 3600) * 1e9),
                "node_capacity_cpu_cores": Decimal(node_cpu_cores),
                "node_capacity_cpu_core_seconds": Decimal(node_cpu_cores * 3600),
                "node_capacity_memory_bytes": Decimal(node_memory_gb * 1e9),
                "node_capacity_memory_byte_seconds": Decimal(node_memory_gb * 1e7 * 3600),
                "pod_labels": self._gen_openshift_labels(report),
                "resource_id": f"i-{resource_id}",
            }
            line_item = OCPUsageLineItem(**data)
            line_item.save()

    def _populate_daily_table(self):
        """Populate the daily table."""
        OCPUsageLineItemDaily.objects.all().delete()
        included_fields = ["namespace", "pod", "node", "pod_labels", "resource_id", "report_period_id"]
        annotations = {
            "usage_start": F("report__interval_start"),
            "usage_end": F("report__interval_start"),
            "pod_usage_cpu_core_seconds": Sum("pod_usage_cpu_core_seconds"),
            "pod_request_cpu_core_seconds": Sum("pod_request_cpu_core_seconds"),
            "pod_limit_cpu_core_seconds": Sum("pod_limit_cpu_core_seconds"),
            "pod_usage_memory_byte_seconds": Sum("pod_usage_memory_byte_seconds"),
            "pod_request_memory_byte_seconds": Sum("pod_request_memory_byte_seconds"),
            "pod_limit_memory_byte_seconds": Sum("pod_limit_memory_byte_seconds"),
            "cluster_id": F("report_period__cluster_id"),
            "cluster_alias": Value(self.cluster_alias, output_field=CharField()),
            "node_capacity_cpu_cores": Max("node_capacity_cpu_cores"),
            "node_capacity_cpu_core_seconds": Max("node_capacity_cpu_core_seconds"),
            "node_capacity_memory_bytes": Max("node_capacity_memory_bytes"),
            "node_capacity_memory_byte_seconds": Max("node_capacity_memory_byte_seconds"),
        }
        entries = OCPUsageLineItem.objects.values(*included_fields).annotate(**annotations)

        cluster_capacity_cpu_core_seconds = Decimal(0)
        cluster_capacity_memory_byte_seconds = Decimal(0)

        cluster_cap = OCPUsageLineItem.objects.values(*["node"]).annotate(
            **{
                "node_capacity_cpu_core_seconds": Max("node_capacity_cpu_core_seconds"),
                "node_capacity_memory_byte_seconds": Sum("node_capacity_memory_byte_seconds"),
            }
        )

        for node in cluster_cap:
            cluster_capacity_cpu_core_seconds += node.get("node_capacity_cpu_core_seconds")
            cluster_capacity_memory_byte_seconds += node.get("node_capacity_memory_byte_seconds")

        for entry in entries:
            entry["total_seconds"] = 3600
            entry["cluster_capacity_cpu_core_seconds"] = cluster_capacity_cpu_core_seconds
            entry["cluster_capacity_memory_byte_seconds"] = cluster_capacity_memory_byte_seconds
            entry["total_capacity_cpu_core_seconds"] = cluster_capacity_cpu_core_seconds
            entry["total_capacity_memory_byte_seconds"] = cluster_capacity_memory_byte_seconds
            daily = OCPUsageLineItemDaily(**entry)
            daily.save()

    def _populate_daily_summary_table(self):
        """Populate the daily summary table."""
        OCPUsageLineItemDailySummary.objects.all().delete()
        included_fields = [
            "usage_start",
            "usage_end",
            "namespace",
            "report_period_id",
            "pod",
            "node",
            "cluster_id",
            "cluster_alias",
            "node_capacity_cpu_cores",
            "pod_labels",
        ]
        annotations = {
            "pod_usage_cpu_core_hours": F("pod_usage_cpu_core_seconds") / 3600,
            "pod_request_cpu_core_hours": Sum(
                ExpressionWrapper(F("pod_request_cpu_core_seconds") / 3600, output_field=DecimalField())
            ),
            "pod_limit_cpu_core_hours": Sum(
                ExpressionWrapper(F("pod_limit_cpu_core_seconds") / 3600, output_field=DecimalField())
            ),
            "pod_usage_memory_gigabyte_hours": Sum(
                ExpressionWrapper(F("pod_usage_memory_byte_seconds") / 3600, output_field=DecimalField())
            )
            * math.pow(2, -30),
            "pod_request_memory_gigabyte_hours": Sum(
                ExpressionWrapper(F("pod_request_memory_byte_seconds") / 3600, output_field=DecimalField())
            )
            * math.pow(2, -30),
            "pod_limit_memory_gigabyte_hours": ExpressionWrapper(
                F("pod_limit_memory_byte_seconds") / 3600, output_field=DecimalField()
            )
            * math.pow(2, -30),
            "node_capacity_cpu_core_hours": F("node_capacity_cpu_core_seconds") / 3600,
            "node_capacity_memory_gigabytes": F("node_capacity_memory_bytes") * math.pow(2, -30),
            "node_capacity_memory_gigabyte_hours": ExpressionWrapper(
                F("node_capacity_memory_byte_seconds") / 3600, output_field=DecimalField()
            )
            * math.pow(2, -30),
            "cluster_capacity_cpu_core_hours": F("cluster_capacity_cpu_core_seconds") / 3600,
            "cluster_capacity_memory_gigabyte_hours": ExpressionWrapper(
                F("cluster_capacity_memory_byte_seconds") / 3600, output_field=DecimalField()
            )
            * math.pow(2, -30),
            "total_capacity_cpu_core_hours": F("cluster_capacity_cpu_core_seconds") / 3600 * 2,
            "total_capacity_memory_gigabyte_hours": ExpressionWrapper(
                F("cluster_capacity_memory_byte_seconds") / 3600 * 2, output_field=DecimalField()
            )
            * math.pow(2, -30),
            "data_source": Value("Pod", output_field=CharField()),
        }

        entries = OCPUsageLineItemDaily.objects.values(*included_fields).annotate(**annotations)

        for entry in entries:
            summary = OCPUsageLineItemDailySummary(**entry)
            summary.save()

    def _populate_charge_info(self):
        """Populate the charge information in summary table."""
        entries = OCPUsageLineItemDailySummary.objects.filter(data_source="Pod").all()
        for entry in entries:
            mem_usage = entry.pod_usage_memory_gigabyte_hours
            mem_request = entry.pod_request_memory_gigabyte_hours
            mem_charge = max(float(mem_usage), float(mem_request)) * 0.25

            entry.pod_charge_memory_gigabyte_hours = mem_charge

            cpu_usage = entry.pod_usage_cpu_core_hours
            cpu_request = entry.pod_request_cpu_core_hours
            cpu_charge = max(float(cpu_usage), float(cpu_request)) * 0.50

            entry.pod_charge_cpu_core_hours = cpu_charge

            entry.save()

    def _populate_monthly_charge_info(self, start_date, node_cost, num_nodes):
        """Populate the charge information in summary table."""
        total_cost = node_cost * num_nodes
        st_date = start_date.date() if isinstance(start_date, datetime) else start_date

        OCPUsageLineItemDailySummary.objects.create(usage_start=st_date, usage_end=st_date, monthly_cost=total_cost)

    def _populate_storage_charge_info(self):
        """Populate the storage charge information in summary table."""
        entries = OCPUsageLineItemDailySummary.objects.filter(data_source="Storage").all()
        for entry in entries:
            storage_usage = entry.persistentvolumeclaim_usage_gigabyte_months
            storage_request = entry.volume_request_storage_gigabyte_months
            storage_charge = float(storage_usage + storage_request) * 0.25

            entry.persistentvolumeclaim_charge_gb_month = storage_charge

            entry.save()

    def _populate_cost_summary_table(self):
        """Populate the cost summary table."""
        CostSummary.objects.all().delete()
        included_fields = [
            "usage_start",
            "usage_end",
            "namespace",
            "pod",
            "node",
            "cluster_id",
            "cluster_alias",
            "pod_labels",
        ]
        usage_annotations = {
            "pod_charge_cpu_core_hours": Coalesce(F("pod_charge_cpu_core_hours"), Decimal(0)),
            "pod_charge_memory_gigabyte_hours": Coalesce(F("pod_charge_memory_gigabyte_hours"), Decimal(0)),
            "infra_cost": Coalesce(F("pod_charge_memory_gigabyte_hours"), Decimal(0)),
            "project_infra_cost": Coalesce(F("pod_charge_memory_gigabyte_hours"), Decimal(0)),
            "persistentvolumeclaim_charge_gb_month": Coalesce(F("pod_charge_memory_gigabyte_hours"), Decimal(0)),
        }

        usage_entries = OCPUsageLineItemDailySummary.objects.values(*included_fields).annotate(**usage_annotations)

        for entry in usage_entries:
            summary = CostSummary(**entry)
            summary.save()
        CostSummary.objects.update(
            markup_cost=(
                (
                    F("pod_charge_cpu_core_hours")
                    + F("pod_charge_memory_gigabyte_hours")
                    + F("persistentvolumeclaim_charge_gb_month")
                    + F("infra_cost")
                )
                * 0.1
            )
        )
        CostSummary.objects.update(
            project_markup_cost=(
                (
                    F("pod_charge_cpu_core_hours")
                    + F("pod_charge_memory_gigabyte_hours")
                    + F("persistentvolumeclaim_charge_gb_month")
                    + F("project_infra_cost")
                )
                * 0.1
            )
        )

    def create_storage_line_items(self, report_period, report):
        """Create OCP hourly usage line items."""
        vol_gb = random.randint(4, 32)
        for row in self.line_items:
            data = {
                "report_period": report_period,
                "report": report,
                "namespace": row.get("namespace"),
                "pod": row.get("pod"),
                "persistentvolumeclaim": row.get("persistentvolumeclaim"),
                "persistentvolume": row.get("persistentvolume"),
                "storageclass": row.get("storageclass"),
                "volume_request_storage_byte_seconds": Decimal(random.uniform(0, 3600) * 1e9),
                "persistentvolumeclaim_usage_byte_seconds": Decimal(random.uniform(0, 3600) * 1e9),
                "persistentvolumeclaim_capacity_bytes": Decimal(vol_gb * 1e9),
                "persistentvolumeclaim_capacity_byte_seconds": Decimal(vol_gb * 1e7 * 3600),
                "persistentvolume_labels": self._gen_openshift_labels(report),
                "persistentvolumeclaim_labels": self._gen_openshift_labels(report),
            }
            line_item = OCPStorageLineItem(**data)
            line_item.save()

    def _populate_storage_daily_table(self):
        """Populate the daily table."""
        included_fields = [
            "namespace",
            "pod",
            "report_period_id",
            "persistentvolumeclaim",
            "persistentvolume",
            "storageclass",
            "persistentvolume_labels",
            "persistentvolumeclaim_labels",
        ]
        annotations = {
            "node": Value(random.choice(self.line_items).get("node"), output_field=CharField()),
            "usage_start": F("report__interval_start"),
            "usage_end": F("report__interval_start"),
            "persistentvolumeclaim_capacity_bytes": Max("persistentvolumeclaim_capacity_bytes"),
            "persistentvolumeclaim_capacity_byte_seconds": Sum("persistentvolumeclaim_capacity_byte_seconds"),
            "volume_request_storage_byte_seconds": Sum("volume_request_storage_byte_seconds"),
            "persistentvolumeclaim_usage_byte_seconds": Sum("persistentvolumeclaim_usage_byte_seconds"),
            "cluster_id": F("report_period__cluster_id"),
            "cluster_alias": Value(self.cluster_alias, output_field=CharField()),
        }
        entries = OCPStorageLineItem.objects.values(*included_fields).annotate(**annotations)

        for entry in entries:
            entry["total_seconds"] = 3600
            daily = OCPStorageLineItemDaily(**entry)
            daily.save()

    def _populate_storage_daily_summary_table(self):
        """Populate the daily summary table."""
        included_fields = [
            "usage_start",
            "usage_end",
            "namespace",
            "report_period_id",
            "pod",
            "node",
            "persistentvolumeclaim",
            "persistentvolume",
            "storageclass",
            "cluster_id",
            "cluster_alias",
        ]
        annotations = {
            "volume_labels": Coalesce(F("persistentvolume_labels"), F("persistentvolumeclaim_labels")),
            "persistentvolumeclaim_capacity_gigabyte": ExpressionWrapper(
                F("persistentvolumeclaim_capacity_bytes") * math.pow(2, -30), output_field=DecimalField()
            ),
            "persistentvolumeclaim_capacity_gigabyte_months": ExpressionWrapper(
                F("persistentvolumeclaim_capacity_byte_seconds") / 86400 * 30 * math.pow(2, -30),
                output_field=DecimalField(),
            ),
            "volume_request_storage_gigabyte_months": ExpressionWrapper(
                F("volume_request_storage_byte_seconds") / 86400 * 30 * math.pow(2, -30), output_field=DecimalField()
            ),
            "persistentvolumeclaim_usage_gigabyte_months": ExpressionWrapper(
                F("persistentvolumeclaim_usage_byte_seconds") / 86400 * 30 * math.pow(2, -30),
                output_field=DecimalField(),
            ),
            "data_source": Value("Storage", output_field=CharField()),
        }

        entries = OCPStorageLineItemDaily.objects.values(*included_fields).annotate(**annotations)

        for entry in entries:
            summary = OCPUsageLineItemDailySummary(**entry)
            summary.save()

    def _populate_pod_label_summary_table(self):
        """Populate pod label key and values."""
        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpusagepodlabel_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": connection.schema_name}
        agg_sql, agg_sql_params = JinjaSql().prepare_query(agg_sql, agg_sql_params)

        with connection.cursor() as cursor:
            cursor.execute(agg_sql)

    def _populate_volume_label_summary_table(self):
        """Populate volume label key and values."""
        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpstoragevolumelabel_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": connection.schema_name}
        agg_sql, agg_sql_params = JinjaSql().prepare_query(agg_sql, agg_sql_params)

        with connection.cursor() as cursor:
            cursor.execute(agg_sql)

    def create_node_label_line_items(self, report_period, report):
        """Create OCP hourly node label line items."""
        for row in self.line_items:
            data = {
                "report_period": report_period,
                "report": report,
                "node": row.get("node"),
                "node_labels": self._gen_openshift_labels(report),
            }
            line_item = OCPNodeLabelLineItem(**data)
            line_item.save()

    def _populate_node_label_daily_table(self):
        """Populate the daily table."""
        included_fields = ["node", "report_period_id", "node_labels"]
        annotations = {
            "usage_start": F("report__interval_start"),
            "usage_end": F("report__interval_start"),
            "cluster_id": F("report_period__cluster_id"),
            "cluster_alias": Value(self.cluster_alias, output_field=CharField()),
        }
        entries = OCPNodeLabelLineItem.objects.values(*included_fields).annotate(**annotations)

        for entry in entries:
            entry["total_seconds"] = 3600
            daily = OCPNodeLabelLineItemDaily(**entry)
            daily.save()
