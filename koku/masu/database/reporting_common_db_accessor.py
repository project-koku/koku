#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Downloader for cost usage reports."""
import django.apps

from masu.database.koku_database_access import KokuDBAccess


class ReportingCommonDBAccessor(KokuDBAccess):
    """Class to interact with customer reporting tables."""

    class ReportingCommonSchema:
        """A container for the shared reporting table objects."""

    def __init__(self, schema_name="public"):
        """Establish the database connection."""
        super().__init__(schema_name)
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
