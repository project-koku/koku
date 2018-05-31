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
"""Tests the ProviderAccess implementation for the Koku consumption."""

from unittest.mock import patch

from django.test import TestCase
from providers.aws.aws_provider import AWSProvider
from providers.provider_access import ProviderAccess


class ProviderAccessTestCase(TestCase):
    """Parent Class for ProviderAccess test cases."""

    def setup(self):
        """Create test case objects."""
        pass

    def tearDown(self):
        """Tear down test case objects."""
        pass

    def test_establish_valid_provider(self):
        """Verify that a valid service is created."""
        provider_name = 'AWS'
        interface = ProviderAccess(provider_name)
        self.assertIsNotNone(interface.service)

    def test_establish_invalid_provider(self):
        """Verify that an invalid service is created."""
        provider_name = 'BAD'
        interface = ProviderAccess(provider_name)
        self.assertIsNone(interface.service)

    def test_get_name(self):
        """Get name of service provider."""
        provider = AWSProvider()
        interface = ProviderAccess(provider.name())
        self.assertEqual(provider.name(), interface.service_name())

    def test_usage_source_ready(self):
        """Get status of cost usage source."""
        provider = 'AWS'
        interface = ProviderAccess(provider)

        credential = 'arn:aws:s3:::my_s3_bucket'
        source_name = 'my_s3_bucket'

        source_ready = False
        with patch.object(AWSProvider, 'cost_usage_source_is_reachable', return_value=True):
            source_ready = interface.cost_usage_source_ready(credential, source_name)
        self.assertTrue(source_ready)
