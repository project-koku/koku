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
from django.utils.translation import ugettext as _

from providers.aws.provider import AWSProvider
from providers.aws_local.provider import AWSLocalProvider
from providers.azure.provider import AzureProvider
from providers.azure_local.provider import AzureLocalProvider
from providers.ocp.provider import OCPProvider
from providers.provider_access import ProviderAccessor, ProviderAccessorError

from rest_framework.serializers import ValidationError


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

    def test_establish_azure_provider(self):
        """Verify that AZURE provider is created."""
        provider_name = 'AZURE'
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, AzureProvider))

    def test_establish_azure_local_provider(self):
        """Verify that AZURE local provider is created."""
        provider_name = 'AZURE-local'
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, AzureLocalProvider))

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

    def test_availability_status(self):
        """Get availability_status for a provider."""
        provider = 'AWS'
        interface = ProviderAccessor(provider)

        credential = 'arn:aws:s3:::my_s3_bucket'
        source_name = 'my_s3_bucket'

        with patch.object(AWSProvider, 'cost_usage_source_is_reachable', return_value=True):
            status = interface.availability_status(credential, source_name)
            self.assertEquals(status.get('availability_status'), 'available')
            self.assertEquals(status.get('availability_status_error'), '')

    def test_availability_status_unavailable(self):
        """Get availability_status for a provider that is unavailable."""
        def error_obj(key, message):
            """Create an error object."""
            error = {
                key: [_(message)]
            }
            return error

        detail_msg = 'Error Msg'
        mock_error = ValidationError(error_obj('err.key', detail_msg))
        provider = 'AWS'
        interface = ProviderAccessor(provider)

        credential = 'arn:aws:s3:::my_s3_bucket'
        source_name = 'my_s3_bucket'

        with patch.object(AWSProvider, 'cost_usage_source_is_reachable', side_effect=mock_error):
            status = interface.availability_status(credential, source_name)
            self.assertEquals(status.get('availability_status'), 'unavailable')
            self.assertEquals(status.get('availability_status_error'), detail_msg)

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
