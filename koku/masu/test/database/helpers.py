#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Helper class for database test classes."""
import csv
import datetime
import io
import random
import uuid
from decimal import Decimal

import django.apps
from dateutil import parser
from dateutil import relativedelta
from django.utils import timezone
from faker import Faker
from model_bakery import baker
from tenant_schemas.utils import schema_context

from koku.database import get_model
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.account_alias_accessor import AccountAliasAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util import common as azure_utils
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus

# A subset of AWS product family values
AWS_PRODUCT_FAMILY = ["Storage", "Compute Instance", "Database Storage", "Database Instance"]


class ReportObjectCreator:
    """Populate report tables with data for testing."""

    fake = Faker()

    def __init__(self, schema):
        """Initialize the report object creation helpler."""
        self.schema = schema
        self.report_schema = ReportSchema(django.apps.apps.get_models())
        self.column_types = self.report_schema.column_types

    def create_cost_entry(self, bill, entry_datetime=None):
        """Create a cost entry database object for test."""
        table_name = AWS_CUR_TABLE_MAP["cost_entry"]
        model = get_model(table_name)
        start_datetime = entry_datetime or self.fake.past_datetime(start_date="-60d")
        end_datetime = start_datetime + datetime.timedelta(hours=1)
        with schema_context(self.schema):
            return baker.make(
                model, bill_id=bill.id, interval_start=start_datetime, interval_end=end_datetime, _fill_optional=True
            )

    def create_cost_entry_bill(self, provider_uuid, bill_date=None):
        """Create a cost entry bill database object for test."""
        table_name = AWS_CUR_TABLE_MAP["bill"]
        model = get_model(table_name)
        data = {}
        if bill_date:
            bill_start = self.make_datetime_aware(bill_date).replace(day=1).date()
            bill_end = bill_start + relativedelta.relativedelta(months=1)

            data["billing_period_start"] = bill_start
            data["billing_period_end"] = bill_end
        with schema_context(self.schema):
            return baker.make(model, provider_id=provider_uuid, finalized_datetime=None, **data, _fill_optional=True)

    def create_cost_entry_pricing(self):
        """Create a cost entry pricing database object for test."""
        table_name = AWS_CUR_TABLE_MAP["pricing"]
        model = get_model(table_name)
        with schema_context(self.schema):
            return baker.make(model, _fill_optional=True)

    def create_cost_entry_product(self, product_family=None):
        """Create a cost entry product database object for test."""
        table_name = AWS_CUR_TABLE_MAP["product"]
        model = get_model(table_name)
        with schema_context(self.schema):
            return baker.make(
                model, product_family=product_family or random.choice(AWS_PRODUCT_FAMILY), _fill_optional=True
            )

    def create_cost_entry_reservation(self, schema=None):
        """Create a cost entry reservation database object for test."""
        table_name = AWS_CUR_TABLE_MAP["reservation"]
        model = get_model(table_name)
        with schema_context(self.schema):
            return baker.make(model, _fill_optional=True)

    def create_cost_entry_line_item(self, bill, cost_entry, product, pricing, reservation, resource_id=None):
        """Create a cost entry line item database object for test."""
        table_name = AWS_CUR_TABLE_MAP["line_item"]
        model = get_model(table_name)
        with schema_context(self.schema):
            return baker.make(
                model,
                cost_entry_bill_id=bill.id,
                cost_entry_id=cost_entry.id,
                cost_entry_product_id=product.id,
                cost_entry_pricing_id=pricing.id,
                cost_entry_reservation_id=reservation.id,
                usage_start=cost_entry.interval_start,
                usage_end=cost_entry.interval_end,
                resource_id=resource_id,
                tags={
                    "environment": random.choice(["dev", "qa", "prod"]),
                    self.fake.pystr()[:8]: self.fake.pystr()[:8],
                },
                _fill_optional=True,
            )

    def create_ocp_report_period(self, provider_uuid, period_date=None, cluster_id=None):
        """Create an OCP report database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]
        model = get_model(table_name)

        period_start = self.make_datetime_aware(self.fake.past_datetime()).date().replace(day=1)
        period_end = period_start + relativedelta.relativedelta(days=random.randint(1, 15))
        data = {
            "cluster_id": cluster_id or self.fake.pystr()[:8],
            "provider_id": provider_uuid,
            "report_period_start": period_start,
            "report_period_end": period_end,
        }

        if period_date:
            period_start = period_date.replace(day=1).date()
            period_end = period_start + relativedelta.relativedelta(months=1)

            data["report_period_start"] = period_start
            data["report_period_end"] = period_end
        with schema_context(self.schema):
            return baker.make(model, **data, _fill_optional=True)

    def create_ocp_report(self, reporting_period, report_datetime=None):
        """Create an OCP reporting period database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["report"]
        model = get_model(table_name)

        data = {"report_period_id": reporting_period.id}
        start_datetime = report_datetime or self.fake.past_datetime(start_date="-60d")
        data["interval_start"] = start_datetime
        data["interval_end"] = start_datetime + relativedelta.relativedelta(hours=+1)
        with schema_context(self.schema):
            return baker.make(model, **data, _fill_optional=True)

    def create_ocp_usage_line_item(
        self, report_period, report, resource_id=None, pod=None, namespace=None, node=None, null_cpu_usage=False
    ):
        """Create an OCP usage line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["line_item"]
        model = get_model(table_name)
        data = {
            "pod_usage_cpu_core_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "pod_request_cpu_core_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "pod_limit_cpu_core_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "pod_usage_memory_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "pod_request_memory_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "pod_limit_memory_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "node_capacity_cpu_cores": self.fake.pydecimal(left_digits=5, right_digits=5),
            "node_capacity_cpu_core_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "node_capacity_memory_bytes": self.fake.pydecimal(left_digits=5, right_digits=5),
            "node_capacity_memory_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
        }
        if resource_id:
            data["resource_id"] = resource_id
        if pod:
            data["pod"] = pod
        if namespace:
            data["namespace"] = namespace
        if node:
            data["node"] = node
        if null_cpu_usage:
            data["pod_usage_cpu_core_seconds"] = None
        with schema_context(self.schema):
            return baker.make(
                model, report_period_id=report_period.id, report_id=report.id, **data, _fill_optional=True
            )

    def create_ocp_storage_line_item(self, report_period, report, pod=None, namespace=None):
        """Create an OCP storage line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]
        model = get_model(table_name)
        data = {
            "persistentvolumeclaim_capacity_bytes": self.fake.pydecimal(left_digits=5, right_digits=5),
            "persistentvolumeclaim_capacity_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "volume_request_storage_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
            "persistentvolumeclaim_usage_byte_seconds": self.fake.pydecimal(left_digits=5, right_digits=5),
        }
        if pod:
            data["pod"] = pod
        if namespace:
            data["namespace"] = namespace
        with schema_context(self.schema):
            return baker.make(
                model, report_period_id=report_period.id, report_id=report.id, **data, _fill_optional=True
            )

    def create_ocp_node_label_line_item(self, report_period, report, node=None):
        """Create an OCP node label line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["node_label_line_item"]
        model = get_model(table_name)
        data = {}
        if node:
            data["node"] = node
        with schema_context(self.schema):
            return baker.make(
                model, report_period_id=report_period.id, report_id=report.id, **data, _fill_optional=True
            )

    def create_columns_for_table_with_bakery(self, table, data={}):
        """Generate data for a table."""
        result = baker.prepare(table, **data, _fill_optional=True).__dict__
        if "id" in result:
            del result["id"]
        del result["_state"]
        return result

    def create_csv_file_stream(self, row):
        """Create a CSV file object for bulk upload testing."""
        file_obj = io.StringIO()
        writer = csv.writer(file_obj, delimiter=",", quoting=csv.QUOTE_MINIMAL, quotechar='"')
        writer.writerow(row)
        file_obj.seek(0)

        return file_obj

    def stringify_datetime(self, dt):
        """Convert datetime to string with AWS formatting."""
        return dt.strftime(Config.AWS_DATETIME_STR_FORMAT)

    def datetimeify_string(self, value):
        """Convert datetime string to datetime with AWS formatting."""
        return datetime.datetime.strptime(value, Config.AWS_DATETIME_STR_FORMAT)

    def make_datetime_aware(self, dt):
        """Add tzinfo to the datetime."""
        if timezone.is_aware(dt):
            return dt
        return timezone.make_aware(dt)

    def create_cost_model(self, provider_uuid, source_type, rates=[], markup={}):
        """Create an OCP rate database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["cost_model"]
        cost_model_map = OCP_REPORT_TABLE_MAP["cost_model_map"]

        data = {
            "uuid": str(uuid.uuid4()),
            "created_timestamp": DateAccessor().today_with_timezone("UTC"),
            "updated_timestamp": DateAccessor().today_with_timezone("UTC"),
            "name": self.fake.pystr()[:8],
            "description": self.fake.pystr(),
            "source_type": source_type,
            "rates": rates,
            "markup": markup,
        }

        with ProviderDBAccessor(provider_uuid) as accessor:
            provider_obj = accessor.get_provider()
        with OCPReportDBAccessor(self.schema) as accessor:
            cost_model_obj = accessor.create_db_object(table_name, data)
            data = {"provider_uuid": provider_obj.uuid, "cost_model_id": cost_model_obj.uuid}
            accessor.create_db_object(cost_model_map, data)
            return cost_model_obj

    def create_ocpawscostlineitem_project_daily_summary(self, account_id, schema):
        """Create an ocpawscostlineitem_project_daily_summary object for test."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_project_daily_summary"]
        model = get_model(table_name)
        with AccountAliasAccessor(account_id, schema) as accessor:
            account_alias = accessor._get_db_obj_query().first()
            data = {
                "account_alias_id": account_alias.id,
                "cost_entry_bill": self.create_cost_entry_bill(str(uuid.uuid4())),
                "usage_start": self.make_datetime_aware(self.fake.past_datetime()),
                "usage_end": self.make_datetime_aware(self.fake.past_datetime()),
            }
        with schema_context(self.schema):
            return baker.make(model, **data, _fill_optional=True)

    def create_awscostentrylineitem_daily_summary(self, account_id, schema, cost_entry_bill, usage_date=None):
        """Create reporting_awscostentrylineitem_daily_summary object for test."""
        table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]
        model = get_model(table_name)
        with AccountAliasAccessor(account_id, schema) as accessor:
            account_alias = accessor._get_db_obj_query().first()
            data = {
                "account_alias_id": account_alias.id,
                "cost_entry_bill": cost_entry_bill,
                "usage_start": self.make_datetime_aware(usage_date or self.fake.past_datetime()),
            }
        with schema_context(self.schema):
            return baker.make(model, **data, _fill_optional=True)

    def create_azure_cost_entry_bill(self, provider_uuid, bill_date=None):
        """Create an Azure cost entry bill database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["bill"]
        model = get_model(table_name)

        data = {}
        fake_bill_date = self.make_datetime_aware(self.fake.past_datetime())
        data["billing_period_start"] = fake_bill_date
        data["billing_period_end"] = fake_bill_date

        if bill_date:
            report_date_range = azure_utils.month_date_range(bill_date)
            bill_start, bill_end = report_date_range.split("-")

            data["billing_period_start"] = self.make_datetime_aware(parser.parse(bill_start))
            data["billing_period_end"] = self.make_datetime_aware(parser.parse(bill_end))

        with schema_context(self.schema):
            return baker.make(model, provider_id=provider_uuid, **data, _fill_optional=True)

    def create_azure_cost_entry_product(self, provider_uuid, instance_id=None):
        """Create an Azure cost entry product database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["product"]
        model = get_model(table_name)
        data = {}
        if instance_id:
            data["instance_id"] = instance_id

        with schema_context(self.schema):
            return baker.make(model, provider_id=provider_uuid, **data, _fill_optional=True)

    def create_azure_meter(self, provider_uuid):
        """Create an Azure meter database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["meter"]
        model = get_model(table_name)
        with schema_context(self.schema):
            return baker.make(model, provider_id=provider_uuid, _fill_optional=True)

    def create_azure_cost_entry_line_item(self, bill, product, meter, usage_date=None):
        """Create an Azure cost entry line item database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["line_item"]
        model = get_model(table_name)

        if usage_date:
            usage_date = usage_date.date() if isinstance(usage_date, datetime.datetime) else usage_date
        else:
            usage_date = (bill.billing_period_start + relativedelta.relativedelta(days=random.randint(1, 15))).date()

        with schema_context(self.schema):
            return baker.make(
                model,
                cost_entry_bill_id=bill.id,
                cost_entry_product_id=product.id,
                meter_id=meter.id,
                usage_date=usage_date,
                tags={
                    "environment": random.choice(["dev", "qa", "prod"]),
                    self.fake.pystr()[:8]: self.fake.pystr()[:8],
                },
                _fill_optional=True,
            )


class ManifestCreationHelper:
    """Helper to setup number of processed files."""

    def __init__(self, manifest_id, num_total_files, assembly_id):
        self._manifest_id = manifest_id
        self._assembly_id = assembly_id
        self._num_total_files = num_total_files
        self._report_files = []

    def __del__(self):
        CostUsageReportStatus.objects.filter(manifest_id=self._manifest_id).delete()
        CostUsageReportManifest.objects.filter(assembly_id=self._assembly_id).delete()

    def generate_one_test_file(self):
        file_cnt = len(self._report_files)
        file_name = f"file_{file_cnt}"
        with ReportStatsDBAccessor(file_name, self._manifest_id):
            print(f"Generating file entry ({file_name}) for manifest {self._manifest_id}")
            self._report_files.append(file_name)
            return file_name
        return None

    def generate_test_report_files(self):
        for file_cnt in range(self._num_total_files):
            file_name = f"file_{file_cnt}"
            with ReportStatsDBAccessor(file_name, self._manifest_id):
                print(f"Generating file entry ({file_name}) for manifest {self._manifest_id}")
                self._report_files.append(file_name)
                return file_name

    def get_report_filenames(self):
        return self._report_files

    def mark_report_file_as_completed(self, report_file):
        with ReportStatsDBAccessor(report_file, self._manifest_id) as stats_accessor:
            stats_accessor.log_last_completed_datetime()

    def process_all_files(self):
        for report_file in self._report_files:
            self.mark_report_file_as_completed(report_file)


def map_django_field_type_to_python_type(field):
    """Map a Django field to its corresponding python type."""
    # This catches several different types of IntegerFields such as:
    # PositiveIntegerField, BigIntegerField,
    if "IntegerField" in field:
        return int
    elif field == "FloatField":
        return float
    elif field == "JSONField":
        return dict
    elif field == "DateTimeField":
        return datetime.datetime
    elif field == "DecimalField":
        return Decimal
    else:
        return str
