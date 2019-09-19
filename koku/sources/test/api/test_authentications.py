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

"""Test the authentications endpoint view."""
import json
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker
from sources.config import Config

from api.provider.models import Sources

faker = Faker()


@override_settings(ROOT_URLCONF='sources.urls')
class AuthenticationsSourceTests(TestCase):
    """Test Cases for the authentications endpoint."""

    def setUp(self):
        """Test case setup."""
        self.test_source_id = 1
        self.test_offset = 2
        self.test_header = Config.SOURCES_FAKE_HEADER
        self.koku_uuid = faker.uuid4()

    def test_post_authentications(self):
        """Test the POST authentications endpoint."""
        subscription_id = {'subscription_id': 'test-subscription-id'}

        params = {
            'source_id': 1,
            'credentials': {'subscription_id': 'test-subscription-id'}
        }
        test_name = 'Azure Test'

        credential_dict = {'credentials': {'client_id': 'test_client',
                                                            'tenant_id': 'test_tenant',
                                                            'client_secret': 'test_secret'}}
        azure_obj = Sources(source_id=self.test_source_id,
                            auth_header=self.test_header,
                            offset=self.test_offset,
                            source_type='AZURE',
                            name=test_name,
                            authentication=credential_dict,
                            billing_source={'data_source': {'resource_group': 'RG1',
                                                            'storage_account': 'test_storage'}})
        azure_obj.save()

        response = self.client.post(reverse('authentications'), json.dumps(params), content_type='application/json')
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertIn(str(subscription_id), str(body))
        expected_authentication = credential_dict
        expected_authentication['credentials']['subscription_id'] = subscription_id.get('subscription_id')
        self.assertEqual(Sources.objects.get(source_id=self.test_source_id).authentication, expected_authentication)
