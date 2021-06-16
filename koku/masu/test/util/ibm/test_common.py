#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the IBM common util."""
from unittest.mock import MagicMock
from unittest.mock import patch

from masu.test import MasuTestCase
from masu.util.ibm import common as util


class TestIBMUtils(MasuTestCase):
    """Tests for IBM utilities."""

    @patch("masu.util.ibm.common.hashlib")
    def test_generate_etag(self, hashlib_mock):
        expected_etag = "hahaha"
        hexdigestable = MagicMock()
        hexdigestable.hexdigest.return_value = expected_etag
        hashlib_mock.md5.return_value = hexdigestable
        self.assertEqual(util.generate_etag("hello_world"), expected_etag)

    def test_generate_assembly_id(self):
        self.assertEqual(util.generate_assembly_id(["uuid", "date", "etag"]), "uuid:date:etag")
