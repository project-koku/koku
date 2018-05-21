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
"""Test the IAM views."""

from random import randint

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .iam_test_case import IamTestCase
from ..models import Customer, User, UserPreference


class UserPreferenceViewtest(IamTestCase):
    """Tests the UserPreference view."""

    def setUp(self):
        """Set up the user view tests."""
        super().setUp()
        self.create_service_admin()

        self.test_data = {'name': 'test-pref',
                          'description': 'test-pref',
                          'preference': {'test-pref': ['a',
                                                       ['b', 'c'],
                                                       {'foo': 'bar'}]}}

        # create customer
        response = self.create_customer(self.customer_data[0])
        customer_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # locate the owner
        customer_uuid = customer_json.get('uuid')
        self.assertIsNotNone(customer_uuid)

        # have customer admin token
        co_token = self.get_customer_owner_token(self.customer_data[0])
        self.assertIsNotNone(co_token)

        # create some users
        self.user_data = []
        for _ in range(0, 5):
            a_user = self.gen_user_data()
            user_response = self.create_user(co_token, a_user)
            user_uuid = user_response.json().get('uuid')
            self.assertIsNotNone(user_uuid)
            a_user['uuid'] = user_uuid
            user_token = self.get_token(a_user['username'],
                                        a_user['password'])
            a_user['token'] = user_token
            self.user_data.append(a_user)

    def tearDown(self):
        """Tear down user tests."""
        super().tearDown()
        Customer.objects.all().delete()
        User.objects.all().delete()
        UserPreference.objects.all().delete()

    def test_get_default_preferences_auth(self):
        """Test that default preferences are available."""
        user_id = randint(0, 4)
        client = APIClient()
        url = reverse('preferences-list',
                      kwargs={'user_uuid': self.user_data[user_id]['uuid']})
        client.credentials(HTTP_AUTHORIZATION=self.user_data[user_id]['token'])
        response = client.get(url)
        results = response.json().get('results')
        self.assertEqual(len(results), 3)

        from django.conf import settings
        default_prefs = [
            {'currency': settings.KOKU_DEFAULT_CURRENCY},
            {'locale': settings.KOKU_DEFAULT_LOCALE},
            {'timezone': settings.KOKU_DEFAULT_TIMEZONE}]

        results_prefs = [r['preference'] for r in results]
        self.assertEqual(results_prefs, default_prefs)

    def test_get_preference_auth_other(self):
        """Test that only your preferences are visible."""
        a_user = self.user_data[0]
        other_user = self.user_data[3]

        client = APIClient()
        url = reverse('preferences-list',
                      kwargs={'user_uuid': a_user['uuid']})
        client.credentials(HTTP_AUTHORIZATION=other_user['token'])
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_preferences_anon(self):
        """Test that preferences are only viewable to authenticated users."""
        user_id = randint(0, 4)
        client = APIClient()
        url = reverse('preferences-list',
                      kwargs={'user_uuid': self.user_data[user_id]['uuid']})
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_preference_detail_auth(self):
        """Test that the authed owner can retrieve preference details."""
        user_id = randint(0, 4)
        user_dict = self.user_data[user_id]
        user = User.objects.get(uuid=user_dict['uuid'])
        pref_id = UserPreference.objects.filter(user=user).first().uuid
        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': user_dict['uuid'],
                              'uuid': pref_id})
        client.credentials(HTTP_AUTHORIZATION=user_dict['token'])
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('preference', response.data)

    def test_get_preference_detail_auth_other(self):
        """Test that an authed non-owner cannot retrieve preference details."""
        a_user_dict = self.user_data[0]
        a_user = User.objects.get(uuid=a_user_dict['uuid'])
        a_pref_id = UserPreference.objects.filter(user=a_user).first().uuid

        other_user_dict = self.user_data[3]

        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': a_user_dict['uuid'],
                              'uuid': a_pref_id})
        client.credentials(HTTP_AUTHORIZATION=other_user_dict['token'])
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_preference_detail_anon(self):
        """Test that anonymous users cannot retrieve preference details."""
        user_id = randint(0, 4)
        user_dict = self.user_data[user_id]
        user = User.objects.get(uuid=user_dict['uuid'])
        pref_id = UserPreference.objects.filter(user=user).first().uuid
        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': user_dict['uuid'],
                              'uuid': pref_id})
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_preference_auth(self):
        """Test that auth'ed user can set prefs."""
        user_id = randint(0, 4)
        client = APIClient()
        url = reverse('preferences-list',
                      kwargs={'user_uuid': self.user_data[user_id]['uuid']})
        client.credentials(HTTP_AUTHORIZATION=self.user_data[user_id]['token'])

        # create a pref
        response = client.post(url, self.test_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # validate we can retrieve details on the new pref
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': self.user_data[user_id]['uuid'],
                              'uuid': response.data['uuid']})
        response = client.get(url)
        self.assertEqual(self.test_data['preference'], response.data['preference'])

    def test_create_preference_auth_other(self):
        """Test that auth'ed user cannot set prefs for other users."""
        a_user_dict = self.user_data[0]
        other_user_dict = self.user_data[3]

        client = APIClient()
        url = reverse('preferences-list',
                      kwargs={'user_uuid': a_user_dict['uuid']})
        client.credentials(HTTP_AUTHORIZATION=other_user_dict['token'])

        response = client.post(url, self.test_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_preference_anon(self):
        """Test that setting prefs requires auth."""
        user_id = randint(0, 4)
        client = APIClient()
        url = reverse('preferences-list',
                      kwargs={'user_uuid': self.user_data[user_id]['uuid']})

        response = client.post(url, self.test_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_preference_auth(self):
        """Test that auth'ed user can delete their prefs."""
        user_id = randint(0, 4)
        user_dict = self.user_data[user_id]
        user = User.objects.get(uuid=user_dict['uuid'])
        pref = UserPreference.objects.filter(user=user).first()

        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': user_dict['uuid'],
                              'uuid': pref.uuid})
        client.credentials(HTTP_AUTHORIZATION=self.user_data[user_id]['token'])

        # delete a pref
        response = client.delete(url, pref.preference, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # validate the pref isn't listed
        url = reverse('preferences-list',
                      kwargs={'user_uuid': self.user_data[user_id]['uuid']})
        response = client.get(url)
        results = response.json().get('results')
        results_prefs = [r['preference'] for r in results]
        self.assertNotIn(pref.preference, results_prefs)

    def test_delete_preference_auth_other(self):
        """Test that an authed non-owner cannot delete unowned preferences."""
        a_user_dict = self.user_data[0]
        a_user = User.objects.get(uuid=a_user_dict['uuid'])
        a_pref_id = UserPreference.objects.filter(user=a_user).first().uuid

        other_user_dict = self.user_data[3]

        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': a_user_dict['uuid'],
                              'uuid': a_pref_id})
        client.credentials(HTTP_AUTHORIZATION=other_user_dict['token'])
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_preference_anon(self):
        """Test that anonymous users cannot delete preference details."""
        user_id = randint(0, 4)
        user_dict = self.user_data[user_id]
        user = User.objects.get(uuid=user_dict['uuid'])
        pref_id = UserPreference.objects.filter(user=user).first().uuid
        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': user_dict['uuid'],
                              'uuid': pref_id})
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_preference_auth(self):
        """Test that auth'ed user can update their prefs."""
        user_id = randint(0, 4)
        user_dict = self.user_data[user_id]
        user = User.objects.get(uuid=user_dict['uuid'])
        pref = UserPreference.objects.filter(user=user).first()

        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': user_dict['uuid'],
                              'uuid': pref.uuid})
        client.credentials(HTTP_AUTHORIZATION=self.user_data[user_id]['token'])

        self.assertNotEqual(self.test_data['name'], pref.name)
        self.assertNotEqual(self.test_data['preference'], pref.preference)

        # update a pref
        response = client.put(url, self.test_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # validate the pref is updated
        response = client.get(url)
        self.assertEqual(self.test_data['name'], response.data['name'])
        self.assertEqual(self.test_data['preference'], response.data['preference'])

    def test_update_preference_auth_other(self):
        """Test that an authed non-owner cannot update unowned preferences."""
        a_user_dict = self.user_data[0]
        a_user = User.objects.get(uuid=a_user_dict['uuid'])
        a_pref_id = UserPreference.objects.filter(user=a_user).first().uuid

        other_user_dict = self.user_data[3]

        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': a_user_dict['uuid'],
                              'uuid': a_pref_id})
        client.credentials(HTTP_AUTHORIZATION=other_user_dict['token'])
        response = client.put(url, self.test_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_preference_anon(self):
        """Test that anonymous users cannot update preference details."""
        user_id = randint(0, 4)
        user_dict = self.user_data[user_id]
        user = User.objects.get(uuid=user_dict['uuid'])
        pref_id = UserPreference.objects.filter(user=user).first().uuid

        client = APIClient()
        url = reverse('preferences-detail',
                      kwargs={'user_uuid': user_dict['uuid'],
                              'uuid': pref_id})
        response = client.put(url, self.test_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
