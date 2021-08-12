#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the currency common."""
import json

from django.test import TestCase

from currency.common import CURRENCY_FILE_NAME
from currency.common import get_choices


class TestCurrencyCommon(TestCase):
    """Test cases for currency common."""

    def test_get_choices(self):
        """Test we get the correct currencies choices."""
        with open(CURRENCY_FILE_NAME) as api_file:
            file_content = json.load(api_file)
        expected = tuple([(c.get("code"), c.get("code")) for c in file_content])
        self.assertEqual(expected, get_choices())
