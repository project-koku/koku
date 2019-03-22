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
"""Tests the ProviderAccessor implementation for the Koku consumption."""

from unittest.mock import patch

from django.test import TestCase
from providers.aws.aws_provider import AWSProvider
from providers.aws_local.aws_local_provider import AWSLocalProvider
from providers.ocp.ocp_provider import OCPProvider
from providers.ocp_local.ocp_local_provider import OCPLocalProvider
from providers.provider_access import ProviderAccessor, ProviderAccessorError


class ProviderAccessorTestCase(TestCase):
    """Parent Class for ProviderAccessor test cases."""

    def setup(self):
        """Create test case objects."""
        pass

    def tearDown(self):
        """Tear down test case objects."""
        pass

    def test_establish_aws_provider(self):
        """Verify that an aws service is created."""
        provider_name = 'AWS'
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)

    def test_establish_ocp_provider(self):
        """Verify that an ocp service is created."""
        provider_name = 'OCP'
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)

    def test_establish_aws_local_provider(self):
        """Verify that AWS local provider is created."""
        provider_name = 'AWS-local'
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, AWSLocalProvider))

    def test_establish_ocp_local_provider(self):
        """Verify that OCP local provider is created."""
        provider_name = 'OCP-local'
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, OCPLocalProvider))

    def test_establish_invalid_provider(self):
        """Verify that an invalid service is created."""
        provider_name = 'BAD'
        interface = ProviderAccessor(provider_name)
        self.assertIsNone(interface.service)

    def test_get_name_aws(self):
        """Get name of aws service provider."""
        provider = AWSProvider()
        interface = ProviderAccessor(provider.name())
        self.assertEqual(provider.name(), interface.service_name())

    def test_get_name_ocp(self):
        """Get name of ocp service provider."""
        provider = OCPProvider()
        interface = ProviderAccessor(provider.name())
        self.assertEqual(provider.name(), interface.service_name())

    def test_usage_source_ready(self):
        """Get status of cost usage source."""
        provider = 'AWS'
        interface = ProviderAccessor(provider)

        credential = 'arn:aws:s3:::my_s3_bucket'
        source_name = 'my_s3_bucket'

        source_ready = False
        with patch.object(AWSProvider, 'cost_usage_source_is_reachable', return_value=True):
            source_ready = interface.cost_usage_source_ready(credential, source_name)
        self.assertTrue(source_ready)

    def test_get_infrastructure_type_exception(self):
        """Get infrastructure type with exception."""
        provider = OCPProvider()
        interface = ProviderAccessor(provider.name())
        with self.assertRaises(ProviderAccessorError):
            with patch.object(OCPProvider, 'infra_type_implementation', side_effect=Exception('test')):
                interface.infrastructure_type(None, None)

    def test_get_infrastructure_key_list_exception(self):
        """Get infrastructure key list with exception."""
        provider = OCPProvider()
        interface = ProviderAccessor(provider.name())
        with self.assertRaises(ProviderAccessorError):
            with patch.object(OCPProvider, 'infra_key_list_implementation', side_effect=Exception('test')):
                interface.infrastructure_type(None, None)
