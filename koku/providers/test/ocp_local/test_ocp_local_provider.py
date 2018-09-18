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
"""Tests the OCPLocalProvider implementation for the Koku interface."""

import os
import tempfile

from django.test import TestCase
from providers.ocp_local.ocp_local_provider import OCPLocalProvider
from rest_framework.exceptions import ValidationError


class OCPLocalProviderTestCase(TestCase):
    """Parent Class for OCPLocalProvider test cases."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()
        self.cur_source = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test case objects."""
        os.rmdir(self.cur_source)

    def test_get_name(self):
        """Get name of provider."""
        provider = OCPLocalProvider()
        self.assertEqual(provider.name(), 'OCP-local')

    def test_cost_usage_source_is_reachable(self):
        """Verify that the cost usage source is authenticated and created."""
        cluster_id = 'my-ocp-cluster-1'
        bucket_name = self.cur_source

        provider_interface = OCPLocalProvider()

        try:
            provider_interface.cost_usage_source_is_reachable(cluster_id, bucket_name)
        except Exception as error:
            self.fail('Unexpected Error: {}'.format(str(error)))

    def test_cost_usage_source_is_not_reachable(self):
        """Verify that the cost usage source is not reachable."""
        cluster_id = 'my-ocp-cluster-1'
        bucket_name = '/bogus/path/'

        provider_interface = OCPLocalProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(cluster_id, bucket_name)
