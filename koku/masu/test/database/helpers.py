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
from decimal import InvalidOperation

import django.apps
from dateutil import parser
from dateutil import relativedelta
from django.utils import timezone
from django_tenants.utils import schema_context
from faker import Faker
from model_bakery import baker

from koku.database import get_model
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportSchema
from masu.util import common as azure_utils

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

    def create_db_object(self, table_name, data):
        """Instantiate a populated database object.

        Args:
            table_name (str): The name of the table to create
            data (dict): A dictionary of data to insert into the object

        Returns:
            (Table): A populated SQLAlchemy table object specified by table_name

        """
        table = getattr(self.report_schema, table_name)
        data = self.clean_data(data, table_name)

        with schema_context(self.schema):
            model_object = table(**data)
            model_object.save()
            return model_object

    def clean_data(self, data, table_name):
        """Clean data for insertion into database.

        Args:
            data (dict): The data to be cleaned
            table_name (str): The table name the data is associated with

        Returns:
            (dict): The data with values converted to required types

        """
        column_types = self.report_schema.column_types[table_name]

        for key, value in data.items():
            if value is None or value == "":
                data[key] = None
                continue
            if column_types.get(key) in [int, "BigIntegerField"]:
                data[key] = self._convert_value(value, int)
            elif column_types.get(key) == float:
                data[key] = self._convert_value(value, float)
            elif column_types.get(key) == Decimal:
                data[key] = self._convert_value(value, Decimal)

        return data

    def _convert_value(self, value, column_type):
        """Convert a single value to the specified column type.

        Args:
            value (var): A value of any type
            column_type (type) A Python type

        Returns:
            (var): The variable converted to type or None if conversion fails.

        """
        if column_type == Decimal:
            try:
                value = Decimal(value).quantize(Decimal(self.decimal_precision))
            except InvalidOperation:
                value = None
        else:
            try:
                value = column_type(value)
            except ValueError:
                value = None
        return value

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

    def create_cost_model(self, provider_uuid, source_type, rates=None, markup=None):
        """Create an OCP rate database object for test."""
        if rates is None:
            rates = []
        if markup is None:
            markup = {}
        table_name = OCP_REPORT_TABLE_MAP["cost_model"]
        cost_model_map = OCP_REPORT_TABLE_MAP["cost_model_map"]

        data = {
            "uuid": str(uuid.uuid4()),
            "created_timestamp": timezone.now(),
            "updated_timestamp": timezone.now(),
            "name": self.fake.pystr()[:8],
            "description": self.fake.pystr(),
            "source_type": source_type,
            "rates": rates,
            "markup": markup,
        }

        cost_model_obj = self.create_db_object(table_name, data)
        data = {"provider_uuid": provider_uuid, "cost_model_id": cost_model_obj.uuid}
        self.create_db_object(cost_model_map, data)
        return cost_model_obj

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
