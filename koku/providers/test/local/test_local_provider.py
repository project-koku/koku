#
# Copyright 2018 Red Hat, Inc.
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
"""Tests the AWSProvider implementation for the Koku interface."""

import os
import tempfile

from django.test import TestCase
from providers.local.local_provider import LocalProvider
from rest_framework.exceptions import ValidationError


class LocalProviderTestCase(TestCase):
    """Parent Class for LocalProvider test cases."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()
        self.cur_source = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test case objects."""
        os.rmdir(self.cur_source)

    def test_get_name(self):
        """Get name of provider."""
        provider = LocalProvider()
        self.assertEqual(provider.name(), 'Local')

    def test_cost_usage_source_is_reachable(self):
        """Verify that the cost usage source is authenticated and created."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = self.cur_source

        provider_interface = LocalProvider()

        try:
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)
        except Exception:
            self.fail('Unexpected Error')

    def test_cost_usage_source_is_not_reachable(self):
        """Verify that the cost usage source is not reachable."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = '/bogus/path/'

        provider_interface = LocalProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)
