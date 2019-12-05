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
"""Tests the AWSLocalProvider implementation for the Koku interface."""

import os
import tempfile

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from providers.aws_local.provider import AWSLocalProvider


class AWSLocalProviderTestCase(TestCase):
    """Parent Class for AWSLocalProvider test cases."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()
        self.cur_source = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test case objects."""
        os.rmdir(self.cur_source)
        super().tearDown()

    def test_get_name(self):
        """Get name of provider."""
        provider = AWSLocalProvider()
        self.assertEqual(provider.name(), 'AWS-local')

    def test_cost_usage_source_is_reachable(self):
        """Verify that the cost usage source is authenticated and created."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = self.cur_source

        provider_interface = AWSLocalProvider()

        try:
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)
        except Exception as error:
            self.fail('Unexpected Error: {}'.format(str(error)))

    def test_cost_usage_source_is_reachable_no_bucket(self):
        """Verify that the cost usage source is not authenticated and created when no bucket is provided."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = None

        provider_interface = AWSLocalProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)
