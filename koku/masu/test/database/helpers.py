#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Helper class for database test classes."""
import uuid

from django_tenants.utils import schema_context
from faker import Faker

from koku.database import get_model
from masu.database import OCP_REPORT_TABLE_MAP
from masu.external.date_accessor import DateAccessor

# A subset of AWS product family values
AWS_PRODUCT_FAMILY = ["Storage", "Compute Instance", "Database Storage", "Database Instance"]


class ReportObjectCreator:
    """Populate report tables with data for testing."""

    fake = Faker()

    def __init__(self, schema):
        """Initialize the report object creation helpler."""
        self.schema = schema

    def create_db_object(self, table_name, data):
        """Instantiate a populated database object.

        Args:
            table_name (str): The name of the table to create
            data (dict): A dictionary of data to insert into the object

        Returns:
            (Table): A populated SQLAlchemy table object specified by table_name

        """
        table = get_model(table_name)

        with schema_context(self.schema):
            model_object = table(**data)
            model_object.save()
            return model_object

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
            "created_timestamp": DateAccessor().today_with_timezone("UTC"),
            "updated_timestamp": DateAccessor().today_with_timezone("UTC"),
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
