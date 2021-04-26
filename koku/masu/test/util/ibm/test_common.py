#
# Copyright 2021 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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
