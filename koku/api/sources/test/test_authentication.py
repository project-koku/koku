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

"""Test the authentication proxy endpoint view."""
import json
import requests
import requests_mock

from django.test import TestCase
from django.urls import reverse
from faker import Faker


faker = Faker()


class AuthenticationProxyTests(TestCase):
    """Test Cases for the billing_source proxy endpoint."""

    def test_post_authentication_proxy(self):
        """Test the POST authentication proxy endpoint."""
        test_source_id = 1
        credentials = {'subscription_id': 'subscription-uuid'}
        with self.settings(SOURCES_CLIENT_BASE_URL='http://www.sourcesclient.com/api/v1'):
            with requests_mock.mock() as m:
                m.post(f'http://www.sourcesclient.com/api/v1/authentication/',
                       status_code=201, json={'source_id': test_source_id,
                                              'credentials': credentials})

                params = {'source_id': test_source_id, 'billing_source': credentials}
                response = self.client.post(reverse('authentication'), json.dumps(params),
                                            content_type='application/json')

                body = response.json()

                self.assertEqual(response.status_code, 201)
                self.assertIn(str(credentials), str(body))


def test_post_authentication_proxy_error(self):
    """Test the POST authentication proxy endpoint with connection error."""
    test_source_id = 1
    credentials = {'subscription_id': 'subscription-uuid'}
    with self.settings(SOURCES_CLIENT_BASE_URL='http://www.sourcesclient.com/api/v1'):
        with requests_mock.mock() as m:
            m.post(f'http://www.sourcesclient.com/api/v1/billing_source/',
                   exc=requests.exceptions.RequestException,
                   json={'source_id': test_source_id, 'credentials': credentials})

            params = {'source_id': test_source_id, 'billing_source': credentials}
            response = self.client.post(reverse('billing-source'), json.dumps(params),
                                        content_type='application/json')

            self.assertEqual(response.status_code, 400)
