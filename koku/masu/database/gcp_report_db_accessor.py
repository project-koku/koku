"""Database accessor for GCP report data."""
import logging

from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryProductService

LOG = logging.getLogger(__name__)


class GCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with GCP Report reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            columns = ["id", "billing_period_start", "provider_id"]
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {(bill["billing_period_start"], bill["provider_id"]): bill["id"] for bill in bills}

    def mark_bill_as_finalized(self, bill_id):
        """Mark a bill in the database as finalized."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            bill = self._get_db_obj_query(table_name).get(id=bill_id)
            if bill.finalized_datetime is None:
                bill.finalized_datetime = self.date_accessor.today_with_timezone("UTC")
                bill.save()

    def get_products(self):
        """Make a mapping of product sku to product objects."""
        table_name = GCPCostEntryProductService
        with schema_context(self.schema):
            columns = ["service_id", "sku_id", "id"]
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {(product["service_id"], product["sku_id"]): product["id"] for product in products}
