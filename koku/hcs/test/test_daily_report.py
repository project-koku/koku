#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCS csv_file_handler."""
import logging

from api.models import Provider
from api.utils import DateHelper
from hcs.daily_report import ReportHCS
from hcs.test import HCSTestCase

LOG = logging.getLogger(__name__)


class TestReportHCS(HCSTestCase):
    """Test cases for HCS Daily Report"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"
        cls.tracing_id = "12345-12345-12345"

    def test_init(self):
        """Test the initializer."""
        dr = ReportHCS(self.schema, self.provider, self.provider_uuid, "12345-12345-12345")
        self.assertEqual(dr._schema_name, "acct10001")
        self.assertEqual(dr._provider, "AWS")
        self.assertEqual(dr._provider_uuid, "cabfdddb-4ed5-421e-a041-311b75daf235")
        self.assertEqual(self.tracing_id, "12345-12345-12345")
