"""Database accessor for GCP report data."""
import logging

from tenant_schemas.utils import schema_context

from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.provider.gcp.models import GCPCostEntryBill, GCPCostEntryLineItemDaily

LOG = logging.getLogger(__name__)


class GCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with GCP Report reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns

        """
        super().__init__(schema, column_map)
        self.column_map = column_map
        self._schema_name = schema

    def get_cost_entry_bills_query_by_provider(self, provider_id):
        """Return all cost entry bills for the specified provider."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(provider_id=provider_id)

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the GCPCostEntryLineItemDaily for a given bill query."""
        table_name = GCPCostEntryLineItemDaily
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return line_item_query
