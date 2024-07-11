#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportDBAccessorBase utility object."""
from unittest.mock import patch

from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.test import MasuTestCase


class ReportDBAccessorBaseTest(MasuTestCase):
    """Test Cases for the ReportDBAccessorBase object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = ReportDBAccessorBase(schema=cls.schema)

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_schema_exists_cache_value_in_cache(self, trino_mock):
        with patch(
            "masu.database.report_db_accessor_base.get_value_from_cache",
            return_value=True,
        ):
            self.assertTrue(self.accessor.schema_exists_trino())
            trino_mock.assert_not_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_schema_exists_cache_value_not_in_cache(self, trino_mock):
        trino_mock.return_value = True
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertTrue(self.accessor.schema_exists_trino())
            mock_cache_set.assert_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_schema_exists_cache_value_not_in_cache_not_exists(self, trino_mock):
        trino_mock.return_value = False
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertFalse(self.accessor.schema_exists_trino())
            mock_cache_set.assert_not_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_table_exists_cache_value_in_cache(self, trino_mock):
        with patch(
            "masu.database.report_db_accessor_base.get_value_from_cache",
            return_value=True,
        ):
            self.assertTrue(self.accessor.table_exists_trino("table"))
            trino_mock.assert_not_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_table_exists_cache_value_not_in_cache(self, trino_mock):
        trino_mock.return_value = True
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertTrue(self.accessor.table_exists_trino("table"))
            mock_cache_set.assert_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_table_exists_cache_value_not_in_cache_not_exists(self, trino_mock):
        trino_mock.return_value = False
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertFalse(self.accessor.table_exists_trino("table"))
            mock_cache_set.assert_not_called()
