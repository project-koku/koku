#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCS csv_file_handler."""
from datetime import timedelta
from unittest.mock import patch

from api.provider.models import Provider
from api.utils import DateHelper
from hcs.daily_report import ReportHCS
from hcs.test import HCSTestCase


class TestReportHCS(HCSTestCase):
    """Test cases for HCS Daily Report"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)
        cls.tracing_id = "12345-12345-12345"

    def test_init(self):
        """Test the initializer."""
        dr = ReportHCS(self.schema, self.aws_provider_type, self.aws_provider_uuid, self.tracing_id)
        self.assertEqual(dr._schema_name, self.schema)
        # the local is stripped off the provider so we are left with the AWS provider
        self.assertEqual(dr._provider, Provider.PROVIDER_AWS)
        self.assertEqual(dr._provider_uuid, self.aws_provider_uuid)
        self.assertEqual(dr._tracing_id, self.tracing_id)

    @patch("hcs.database.report_db_accessor.HCSReportDBAccessor.get_hcs_daily_summary")
    @patch("hcs.database.report_db_accessor.HCSReportDBAccessor.schema_exists_trino")
    def test_bad_schema(self, mock_schema, mock_daily_summary):
        """Test that a schema that does not exist does not call get_hcs_daily_summary."""
        mock_schema.return_value = False
        reporter = ReportHCS(self.schema, self.aws_provider_type, self.aws_provider_uuid, self.tracing_id)
        reporter.generate_report(self.yesterday, self.today)
        mock_daily_summary.assert_not_called()
