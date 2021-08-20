#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Reporting Common."""
import copy
import unittest

from masu.database import AWS_CUR_TABLE_MAP
from reporting_common import REPORT_COLUMN_MAP


class TestReportingCommon(unittest.TestCase):
    """Test Reporting Common."""

    def setUp(self):
        """Set up the test class with required objects."""
        self.report_tables = list(AWS_CUR_TABLE_MAP.values())

    def test_generate_column_map(self):
        """Assert all tables are in the column map."""
        keys = REPORT_COLUMN_MAP.keys()

        tables = copy.deepcopy(self.report_tables)
        tables.remove(AWS_CUR_TABLE_MAP["cost_entry"])
        tables.remove(AWS_CUR_TABLE_MAP["line_item_daily"])
        tables.remove(AWS_CUR_TABLE_MAP["line_item_daily_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["tags_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["ocp_on_aws_project_daily_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["ocp_on_aws_tags_summary"])
        for table in tables:
            self.assertIn(table, keys)
