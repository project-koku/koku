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
"""Test the User views."""

from random import randint

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .iam_test_case import IamTestCase
from ..models import Customer, ResetToken, User


class UserViewTest(IamTestCase):
    """Tests the user view."""

    def setUp(self):
        """Set up the user view tests."""
        super().setUp()
        self.create_service_admin()
        self.customers = []

        for customer in self.customer_data:
            response = self.create_customer(customer)
            customer_json = response.json()
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            customer_uuid = customer_json.get('uuid')
            owner = customer_json.get('owner')
            self.assertIsNotNone(customer_uuid)
            self.assertIsNotNone(owner)
            co_token = self.get_customer_owner_token(customer)
            owner['token'] = co_token
            customer_json['users'] = []
            num_users = randint(1, 5)
            for _ in range(0, num_users):
                a_user = self.gen_user_data()
                user_response = self.create_user(co_token, a_user)
                user_json = user_response.json()
                user_uuid = user_json.get('uuid')
                self.assertIsNotNone(user_uuid)
                a_user['uuid'] = user_uuid
                user_token = self.get_token(a_user['username'],
                                            a_user['password'])
                a_user['token'] = user_token
                db_user_qs = User.objects.filter(uuid=user_uuid)
                self.assertEqual(db_user_qs.count(), 1)
                db_user = db_user_qs.first()
                reset_token_qs = ResetToken.objects.filter(user=db_user)
                self.assertEqual(reset_token_qs.count(), 1)
                reset_token = reset_token_qs.first()
                a_user['reset_token'] = reset_token.token
                customer_json['users'].append(a_user)
            customer_json['users'].append(owner)
            self.customers.append(customer_json)

    def tearDown(self):
        """Tear down user tests."""
        super().tearDown()
        Customer.objects.all().delete()
        User.objects.all().delete()

    def test_get_user_list(self):
        """Test get user list with a customer owner."""
        token = self.customers[0]['owner']['token']
        url = reverse('user-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNotNone(results)
        sorted_users = sorted(self.customers[0]['users'],
                              key=lambda user: user['username'])
        user_count = len(sorted_users)
        self.assertEqual(len(results), user_count)
        for useridx in range(0, user_count):
            self.assertEqual(results[useridx]['username'],
                             sorted_users[useridx]['username'])

    def test_get_user_list_auth(self):
        """Test get user list with a regular user."""
        test_user = self.customers[0]['users'][0]
        token = test_user['token']
        url = reverse('user-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNotNone(results)
        sorted_users = sorted(self.customers[0]['users'],
                              key=lambda user: user['username'])
        user_count = len(sorted_users)
        self.assertEqual(len(results), user_count)
        for useridx in range(0, user_count):
            self.assertEqual(results[useridx]['username'],
                             sorted_users[useridx]['username'])

    def test_get_user_list_anon(self):
        """Test get user list with a anonymous user."""
        url = reverse('user-list')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_user_detail(self):
        """Test get user detail with a customer owner."""
        token = self.customers[0]['owner']['token']
        first = self.customers[0]['users'][0]
        url = reverse('user-detail', args=[first['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        json_result = response.json()

        self.assertEqual(json_result['username'], first['username'])
        self.assertEqual(json_result['email'], first['email'])
        # ensure passwords don't leak
        self.assertIsNone(json_result.get('password'))

    def test_get_user_detail_auth(self):
        """Test get user detail with a regular user."""
        test_user = self.customers[0]['users'][0]
        token = test_user['token']
        url = reverse('user-detail', args=[test_user['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        json_result = response.json()

        self.assertEqual(json_result['username'], test_user['username'])
        self.assertEqual(json_result['email'], test_user['email'])
        # ensure passwords don't leak
        self.assertIsNone(json_result.get('password'))

    def test_get_user_detail_anon(self):
        """Test get user detail with an anonymous user."""
        first = self.customers[0]['users'][0]
        url = reverse('user-detail', args=[first['uuid']])
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_user_diff_customer(self):
        """Test get user detail with a user for a user in another customer."""
        test_user = self.customers[0]['users'][0]
        token = test_user['token']
        other_customer_user = self.customers[1]['users'][0]
        url = reverse('user-detail', args=[other_customer_user['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_reg_user(self):
        """Test create user with a non-customer owner."""
        test_user = self.customers[0]['users'][0]
        token = test_user['token']
        response = self.create_user(token, self.gen_user_data())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_with_owner(self):
        """Test delete user with a customer owner."""
        owner = self.customers[0]['owner']
        token = owner['token']
        test_user = self.customers[0]['users'][0]
        url = reverse('user-detail', args=[test_user['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_reg_user(self):
        """Test delete user with a non-customer owner."""
        test_user = self.customers[0]['users'][0]
        token = test_user['token']
        url = reverse('user-detail', args=[test_user['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reset_password(self):
        """Test reset password with valid user and token."""
        test_user = self.customers[0]['users'][0]
        reset_body = {'token': test_user['reset_token'],
                      'password': self.gen_password()}
        url = reverse('user-reset-password', args=[test_user['uuid']])
        client = APIClient()
        response = client.put(url, data=reset_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reset_password_same_pass(self):
        """Test reset password with valid user, token and same password."""
        test_user = self.customers[0]['users'][0]
        reset_body = {'token': test_user['reset_token'],
                      'password': test_user['password']}
        url = reverse('user-reset-password', args=[test_user['uuid']])
        client = APIClient()
        response = client.put(url, data=reset_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_password_no_reuse(self):
        """Test reset password with valid user and token twice."""
        test_user = self.customers[1]['users'][0]
        reset_body = {'token': test_user['reset_token'],
                      'password': self.gen_password()}
        url = reverse('user-reset-password', args=[test_user['uuid']])
        client = APIClient()
        response = client.put(url, data=reset_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = client.put(url, data=reset_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_password_invalid_token(self):
        """Test reset password with valid user and invalid token."""
        test_user = self.customers[1]['users'][0]
        reset_body = {'token': 'invalid',
                      'password': self.gen_password()}
        url = reverse('user-reset-password', args=[test_user['uuid']])
        client = APIClient()
        response = client.put(url, data=reset_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_password_expired_token(self):
        """Test reset password with valid user and expired token."""
        test_user = self.customers[1]['users'][0]
        reset_body = {'token': test_user['reset_token'],
                      'password': self.gen_password()}
        rt_qs = ResetToken.objects.filter(token=test_user['reset_token'])
        self.assertEqual(rt_qs.count(), 1)
        reset_token = rt_qs.first()
        yesterday = timezone.now() - timezone.timedelta(days=1)
        reset_token.expiration_date = yesterday
        reset_token.save()
        url = reverse('user-reset-password', args=[test_user['uuid']])
        client = APIClient()
        response = client.put(url, data=reset_body, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_current_user(self):
        """Test getting current user."""
        test_user = self.customers[1]['users'][0]
        token = test_user['token']
        url = reverse('user-current')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_current_user_anon(self):
        """Test getting current user with an anonymous user."""
        url = reverse('user-current')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
