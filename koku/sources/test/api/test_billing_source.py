#
# Copyright 2019 Red Hat, Inc.
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

"""Test the billing_source endpoint view."""
import json

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker
from sources.config import Config
from sources.storage import add_provider_sources_network_info

from api.provider.models import Sources

faker = Faker()


@override_settings(ROOT_URLCONF='sources.urls')
class BillingSourceTests(TestCase):
    """Test Cases for the billing_source endpoint."""

    def setUp(self):
        """Test case setup."""
        self.test_source_id = 1
        self.test_offset = 2
        self.test_header = Config.SOURCES_FAKE_HEADER
        self.koku_uuid = faker.uuid4()
        self.test_obj = Sources(source_id=self.test_source_id,
                                auth_header=self.test_header,
                                offset=self.test_offset,
                                koku_uuid=self.koku_uuid)
        self.test_obj.save()

    def test_post_billing_source(self):
        """Test the POST billing_source endpoint."""
        billing_source = {'bucket': 'cost-usage-bucket'}
        test_name = 'AWS Test'
        test_source_type = 'AWS'
        test_source_id = 1
        test_resource_id = 1

        test_matrix = [{'source_id': test_source_id, 'billing_source': billing_source},
                       {'source_name': test_name, 'billing_source': billing_source}]
        for params in test_matrix:
            add_provider_sources_network_info(self.test_source_id, test_name, test_source_type, test_resource_id)
            response = self.client.post(reverse('billing-source'), json.dumps(params), content_type='application/json')
            body = response.json()

            self.assertEqual(response.status_code, 201)
            self.assertIn(str(billing_source), str(body))
            self.assertEqual(Sources.objects.get(source_id=self.test_source_id).billing_source, billing_source)

    def test_post_billing_source_non_aws(self):
        """Test the POST billing_source endpoint for a non-AWS source."""
        params = {
            'source_id': '1',
            'billing_source': {'bucket': 'cost-usage-bucket'},
        }
        expected_string = 'Source is not AWS nor AZURE.'
        test_name = 'OCP Test'
        test_source_type = 'OCP'
        test_resource_id = 1
        add_provider_sources_network_info(self.test_source_id, test_name, test_source_type, test_resource_id)
        response = self.client.post(reverse('billing-source'), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_string, str(body))

    def test_post_billing_source_not_found(self):
        """Test the POST billing_source endpoint for a non-existent source."""
        params = {
            'source_id': '2',
            'billing_source': {'bucket': 'cost-usage-bucket'},
        }
        expected_string = 'does not exist'
        response = self.client.post(reverse('billing-source'), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_string, str(body))
