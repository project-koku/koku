#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCS csv_file_handler."""
from hcs.exceptions import HCSTableNotFoundError
from hcs.test import HCSTestCase


class TestHCSExceptions(HCSTestCase):
    """Test cases for HCS Daily Report"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    def test_HCSTableNotFoundError_init(self):
        """Test HCSTableNotFoundError exception initialization"""
        test_table = "bad_table"
        htfe = HCSTableNotFoundError(test_table)

        self.assertEqual(htfe.table_name, test_table)
        self.assertEqual(htfe.message, "table not found")

    def test_HCSTableNotFoundError_str(self):
        """Test HCSTableNotFoundError exception string"""
        test_table = "bad_table"
        htfe = HCSTableNotFoundError(test_table)

        result = htfe.__str__()
        self.assertEqual(result, "bad_table table not found")
