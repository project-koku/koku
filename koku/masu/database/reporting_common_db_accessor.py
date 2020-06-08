#
# Copyright 2018 Red Hat, Inc.
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
"""Downloader for cost usage reports."""
import django.apps

from masu.database.koku_database_access import KokuDBAccess


class ReportingCommonDBAccessor(KokuDBAccess):
    """Class to interact with customer reporting tables."""

    class ReportingCommonSchema:
        """A container for the shared reporting table objects."""

    def __init__(self, schema="public"):
        """Establish the database connection."""
        super().__init__(schema)
        self.report_common_schema = self.ReportingCommonSchema()
        self._get_reporting_tables()

    def _get_reporting_tables(self):
        """Load table objects for reference and creation."""
        models = django.apps.apps.get_models()

        for model in models:
            if "reporting_common" in model._meta.db_table:
                setattr(self.report_common_schema, model._meta.db_table, model)

            if "region_mapping" in model._meta.db_table:
                setattr(self, f"_{model._meta.db_table}", model)

    def _get_db_obj_query(self, table_name):
        """Create a query for a database object.

        Args:
            table_name (str): The name of the table to create

        Returns:
            (Query): A SQLALchemy query object on the table

        """
        table = getattr(self.report_common_schema, table_name)
        return table.objects.all()

    def add(self, table, fields):
        """
        Add a new row to the database.

        Args:
            table (string): Table name
            fields (dict): Fields containing attributes.
                    Valid keys are the table's fields.

        Returns:
            None

        """
        getattr(self, f"_{table.lower()}").create(**fields)
