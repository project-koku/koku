"""Database accessor for GCP report data."""
import logging

from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting_common import REPORT_COLUMN_MAP

LOG = logging.getLogger(__name__)


class GCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with GCP Report reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self.column_map = REPORT_COLUMN_MAP
