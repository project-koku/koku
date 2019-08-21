#
# Copyright 2019 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Database accessor for Azure report data."""
import logging


from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.azure.models import (AzureCostEntryBill,
                                             AzureCostEntryProduct,
                                             AzureMeter,
                                             AzureService)

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class AzureReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with Azure Report reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns

        """
        super().__init__(schema, column_map)
        self._datetime_format = Config.AZURE_DATETIME_STR_FORMAT
        self.column_map = column_map
        self._schema_name = schema
        self.date_accessor = DateAccessor()

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            columns = ['id', 'subscription_guid', 'billing_period_start', 'provider_id']
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {(bill['subscription_guid'], bill['billing_period_start'],
                     bill['provider_id']): bill['id']
                    for bill in bills}

    def get_products(self):
        """Make a mapping of product objects."""
        table_name = AzureCostEntryProduct
        with schema_context(self.schema):
            columns = ['id', 'instance_id']
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {(product['instance_id']): product['id']
                    for product in products}

    def get_meters(self):
        """Make a mapping of meter objects."""
        table_name = AzureMeter
        with schema_context(self.schema):
            columns = ['id', 'meter_id']
            meters = self._get_db_obj_query(table_name, columns=columns).all()

            return {(meter['meter_id']): meter['id']
                    for meter in meters}

    def get_services(self):
        """Make a mapping of service objects."""
        table_name = AzureService
        with schema_context(self.schema):
            columns = ['id', 'service_tier', 'service_name']
            services = self._get_db_obj_query(table_name, columns=columns).all()

            return {(service['service_tier'], service['service_name']): service['id']
                    for service in services}
