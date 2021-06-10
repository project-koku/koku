#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportingCommonDBAccessor utility object."""
from unittest.mock import Mock

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase


class ReportingCommonDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportingCommonDBAccessor object."""

    def setUp(self):
        """Set up the test class with required objects."""
        super().setUp()
        self.accessor = ReportingCommonDBAccessor()
        self.report_tables = list(AWS_CUR_TABLE_MAP.values())

    def test_add(self):
        """Test the add() function."""
        with ReportingCommonDBAccessor() as accessor:
            accessor._test = Mock()
            accessor.add("test", {"foo": "bar"})
