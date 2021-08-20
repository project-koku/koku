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

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.account_alias_accessor import AccountAliasAccessor
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util import common as azure_utils
from reporting_common import REPORT_COLUMN_MAP
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
        if entry_datetime:
            start_datetime = entry_datetime
        else:
            start_datetime = self.fake.past_datetime(start_date="-60d")
        end_datetime = start_datetime + datetime.timedelta(hours=1)
        data = {"bill_id": bill.id, "interval_start": start_datetime, "interval_end": end_datetime}
        with AWSReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_cost_entry_bill(self, provider_uuid, bill_date=None):
        """Create a cost entry bill database object for test."""
        table_name = AWS_CUR_TABLE_MAP["bill"]
        data = self.create_columns_for_table(table_name)
        data["provider_id"] = provider_uuid
        if bill_date:
            bill_start = self.make_datetime_aware(bill_date).replace(day=1).date()
            bill_end = bill_start + relativedelta.relativedelta(months=1)

            data["billing_period_start"] = bill_start
            data["billing_period_end"] = bill_end

        with AWSReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_cost_entry_pricing(self):
        """Create a cost entry pricing database object for test."""
        table_name = AWS_CUR_TABLE_MAP["pricing"]
        data = self.create_columns_for_table(table_name)
        with AWSReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_cost_entry_product(self, product_family=None):
        """Create a cost entry product database object for test."""
        table_name = AWS_CUR_TABLE_MAP["product"]
        data = self.create_columns_for_table(table_name)
        prod_fam = {"product_family": product_family if product_family else random.choice(AWS_PRODUCT_FAMILY)}
        data.update(prod_fam)
        with AWSReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_cost_entry_reservation(self, schema=None):
        """Create a cost entry reservation database object for test."""
        table_name = AWS_CUR_TABLE_MAP["reservation"]
        data = self.create_columns_for_table(table_name)
        with AWSReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_cost_entry_line_item(self, bill, cost_entry, product, pricing, reservation, resource_id=None):
        """Create a cost entry line item database object for test."""
        table_name = AWS_CUR_TABLE_MAP["line_item"]
        data = self.create_columns_for_table(table_name)
        extra_data = {
            "cost_entry_bill_id": bill.id,
            "cost_entry_id": cost_entry.id,
            "cost_entry_product_id": product.id,
            "cost_entry_pricing_id": pricing.id,
            "cost_entry_reservation_id": reservation.id,
            "usage_start": cost_entry.interval_start,
            "usage_end": cost_entry.interval_end,
            "usage_account_id": self.fake.pystr()[:8],
            "resource_id": resource_id,
            "tags": {
                "environment": random.choice(["dev", "qa", "prod"]),
                self.fake.pystr()[:8]: self.fake.pystr()[:8],
            },
        }

        data.update(extra_data)
        with AWSReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_ocp_report_period(self, provider_uuid, period_date=None, cluster_id=None):
        """Create an OCP report database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]

        period_start = self.make_datetime_aware(self.fake.past_datetime()).date().replace(day=1)
        period_end = period_start + relativedelta.relativedelta(days=random.randint(1, 15))
        data = {
            "cluster_id": cluster_id if cluster_id else self.fake.pystr()[:8],
            "provider_id": provider_uuid,
            "report_period_start": period_start,
            "report_period_end": period_end,
        }

        if period_date:
            period_start = period_date.replace(day=1).date()
            period_end = period_start + relativedelta.relativedelta(months=1)

            data["report_period_start"] = period_start
            data["report_period_end"] = period_end
        with OCPReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_ocp_report(self, reporting_period, report_datetime=None):
        """Create an OCP reporting period database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["report"]

        data = {"report_period_id": reporting_period.id}
        if report_datetime:
            start_datetime = report_datetime
        else:
            start_datetime = self.fake.past_datetime(start_date="-60d")
        data["interval_start"] = start_datetime
        data["interval_end"] = start_datetime + relativedelta.relativedelta(hours=+1)
        with OCPReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_ocp_usage_line_item(
        self, report_period, report, resource_id=None, pod=None, namespace=None, node=None, null_cpu_usage=False
    ):
        """Create an OCP usage line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["line_item"]
        data = self.create_columns_for_table(table_name)

        for key in data:
            if "byte" in key:
                data[key] = data[key] * Decimal(pow(2, 30))

        if resource_id:
            data["resource_id"] = resource_id

        data["report_period_id"] = report_period.id
        data["report_id"] = report.id
        if null_cpu_usage:
            data["pod_usage_cpu_core_seconds"] = None
        if pod:
            data["pod"] = pod
        if namespace:
            data["namespace"] = namespace
        if node:
            data["node"] = node
        with OCPReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_ocp_storage_line_item(self, report_period, report, pod=None, namespace=None):
        """Create an OCP storage line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]
        data = self.create_columns_for_table(table_name)

        for key in data:
            if "bytes" in key or "byte" in key:
                data[key] = data[key] * Decimal(pow(2, 30)) * 5

        data["report_period_id"] = report_period.id
        data["report_id"] = report.id
        if pod:
            data["pod"] = pod
        if namespace:
            data["namespace"] = namespace
        with OCPReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_ocp_node_label_line_item(self, report_period, report, node=None, node_labels=None):
        """Create an OCP node label line item database object for test."""
        table_name = OCP_REPORT_TABLE_MAP["node_label_line_item"]
        data = self.create_columns_for_table(table_name)
        data["report_period_id"] = report_period.id
        data["report_id"] = report.id
        if node:
            data["node"] = node
        with OCPReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_columns_for_table(self, table):
        """Generate data for a table."""
        data = {}
        columns = REPORT_COLUMN_MAP[table].values()
        column_types = self.column_types[table]

        for column in columns:
            col_type = column_types[column]
            # This catches several different types of IntegerFields such as:
            # PositiveIntegerField, BigIntegerField,
            if "IntegerField" in col_type:
                data[column] = self.fake.pyint()
            elif col_type == "FloatField":
                data[column] = self.fake.pyfloat()
            elif col_type == "JSONField":
                data[column] = {"label_one": self.fake.pystr()[:8], "label_two": self.fake.pystr()[:8]}
            elif col_type == "DateTimeField":
                data[column] = self.make_datetime_aware(self.fake.past_datetime())
            elif col_type == "DecimalField":
                data[column] = self.fake.pydecimal(0, 7, positive=True)
            elif col_type == "UUIDField":
                data[column] = self.fake.uuid4()
            else:
                data[column] = self.fake.pystr()[:8]

        return data

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
        data = self.create_columns_for_table(table_name)

        with AccountAliasAccessor(account_id, schema) as accessor:
            account_alias = accessor._get_db_obj_query().first()

            data = {
                "account_alias_id": account_alias.id,
                "cost_entry_bill": self.create_cost_entry_bill(str(uuid.uuid4())),
                "namespace": self.fake.pystr()[:8],
                "pod": self.fake.pystr()[:8],
                "node": self.fake.pystr()[:8],
                "usage_start": self.make_datetime_aware(self.fake.past_datetime()),
                "usage_end": self.make_datetime_aware(self.fake.past_datetime()),
                "product_code": self.fake.pystr()[:8],
                "usage_account_id": self.fake.pystr()[:8],
            }
        with OCPReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_awscostentrylineitem_daily_summary(self, account_id, schema, cost_entry_bill, usage_date=None):
        """Create reporting_awscostentrylineitem_daily_summary object for test."""
        table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]
        data = self.create_columns_for_table(table_name)
        if usage_date is None:
            usage_date = self.fake.past_datetime()

        with AccountAliasAccessor(account_id, schema) as accessor:
            account_alias = accessor._get_db_obj_query().first()
            data = {
                "account_alias_id": account_alias.id,
                "cost_entry_bill": cost_entry_bill,
                "usage_start": self.make_datetime_aware(usage_date),
                "product_code": self.fake.pystr()[:8],
                "usage_account_id": self.fake.pystr()[:8],
            }

        with OCPReportDBAccessor(self.schema) as accessor:
            obj = accessor.create_db_object(table_name, data)
        return obj

    def create_azure_cost_entry_bill(self, provider_uuid, bill_date=None):
        """Create an Azure cost entry bill database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["bill"]
        data = self.create_columns_for_table(table_name)
        data["provider_id"] = provider_uuid
        fake_bill_date = self.make_datetime_aware(self.fake.past_datetime())
        data["billing_period_start"] = fake_bill_date
        data["billing_period_end"] = fake_bill_date

        if bill_date:
            report_date_range = azure_utils.month_date_range(bill_date)
            bill_start, bill_end = report_date_range.split("-")

            data["billing_period_start"] = self.make_datetime_aware(parser.parse(bill_start))
            data["billing_period_end"] = self.make_datetime_aware(parser.parse(bill_end))

        with AzureReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_azure_cost_entry_product(self, provider_uuid, instance_id=None):
        """Create an Azure cost entry product database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["product"]
        data = self.create_columns_for_table(table_name)
        data["provider_id"] = provider_uuid
        if instance_id:
            data["instance_id"] = instance_id

        with AzureReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_azure_meter(self, provider_uuid):
        """Create an Azure meter database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["meter"]
        data = self.create_columns_for_table(table_name)
        data["provider_id"] = provider_uuid

        with AzureReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)

    def create_azure_cost_entry_line_item(self, bill, product, meter, usage_date=None):
        """Create an Azure cost entry line item database object for test."""
        table_name = AZURE_REPORT_TABLE_MAP["line_item"]
        data = self.create_columns_for_table(table_name)

        if usage_date:
            usage_date = usage_date.date() if isinstance(usage_date, datetime.datetime) else usage_date
        else:
            usage_date = (bill.billing_period_start + relativedelta.relativedelta(days=random.randint(1, 15))).date()

        extra_data = {
            "cost_entry_bill_id": bill.id,
            "cost_entry_product_id": product.id,
            "meter_id": meter.id,
            "usage_date": usage_date,
            "tags": {
                "environment": random.choice(["dev", "qa", "prod"]),
                self.fake.pystr()[:8]: self.fake.pystr()[:8],
            },
        }

        data.update(extra_data)
        with AzureReportDBAccessor(self.schema) as accessor:
            return accessor.create_db_object(table_name, data)


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
        field_type = int
    elif field == "FloatField":
        field_type = float
    elif field == "JSONField":
        field_type = dict
    elif field == "DateTimeField":
        field_type = datetime.datetime
    elif field == "DecimalField":
        field_type = Decimal
    else:
        field_type = str
    return field_type
