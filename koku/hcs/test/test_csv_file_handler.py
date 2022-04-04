#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCS csv_file_handler."""
import logging

from api.models import Provider
from api.utils import DateHelper
from hcs.csv_file_handler import CSVFileHandler
from hcs.test import HCSTestCase

LOG = logging.getLogger(__name__)


class TestHCSCSVFileHandler(HCSTestCase):
    """Test cases for HCS CSV File Handler"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

    def test_init(self):
        """Test the initializer."""
        fh = CSVFileHandler(self.schema, self.provider, self.provider_uuid)
        self.assertEqual(fh._schema_name, "10001")
        self.assertEqual(fh._provider, "AWS")
        self.assertEqual(fh._provider_uuid, "cabfdddb-4ed5-421e-a041-311b75daf235")
