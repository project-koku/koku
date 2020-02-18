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
"""Test the User Preference views."""
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient

from ..models import User
from ..models import UserPreference
from ..serializers import UserSerializer
from .iam_test_case import IamTestCase


class UserPreferenceViewTest(IamTestCase):
    """Tests the UserPreference view."""

    fake = Faker()

    def setUp(self):
        """Set up the user view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        self.user = User.objects.get(username=self.user_data["username"])
        self.test_data = {
            "name": "test-pref",
            "description": "test-pref",
            "preference": {
                "test-pref": [
                    self.fake.word(),
                    [self.fake.word(), self.fake.word()],
                    {self.fake.word(): self.fake.text()},
                ]
            },
        }

    def test_get_default_preferences_auth(self):
        """Test that default preferences are available."""
        client = APIClient()
        url = reverse("preferences-list")
        response = client.get(url, **self.headers)
        results = response.json().get("data")
        self.assertEqual(len(results), 3)

        from django.conf import settings

        default_prefs = [
            {"currency": settings.KOKU_DEFAULT_CURRENCY},
            {"locale": settings.KOKU_DEFAULT_LOCALE},
            {"timezone": settings.KOKU_DEFAULT_TIMEZONE},
        ]

        results_prefs = [r["preference"] for r in results]
        self.assertEqual(results_prefs, default_prefs)

    def test_get_preference_detail_auth(self):
        """Test that the authed owner can retrieve preference details."""
        pref_id = UserPreference.objects.filter(user=self.user).first().uuid
        client = APIClient()
        url = reverse("preferences-detail", kwargs={"uuid": pref_id})
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("preference", response.data)

    def test_get_preference_detail_auth_other(self):
        """Test that an authed non-owner cannot retrieve preference details."""
        a_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data, a_user_dict, False)
        serializer = UserSerializer(data=a_user_dict, context=request_context)
        if serializer.is_valid(raise_exception=True):
            other_user = serializer.save()

        a_pref_id = UserPreference.objects.filter(user=other_user).first().uuid
        client = APIClient()
        url = reverse("preferences-detail", kwargs={"uuid": a_pref_id})
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_preference_auth(self):
        """Test that auth'ed user can set prefs."""
        client = APIClient()
        url = reverse("preferences-list")

        # create a pref
        response = client.post(url, self.test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # validate we can retrieve details on the new pref
        url = reverse("preferences-detail", kwargs={"uuid": response.data["uuid"]})
        response = client.get(url, **self.headers)
        self.assertEqual(self.test_data["preference"], response.data["preference"])

    def test_create_preference_null(self):
        """Test that auth'ed user cannot create a prefs with null."""
        client = APIClient()
        url = reverse("preferences-list")
        self.test_data["preference"] = None
        # create a pref
        response = client.post(url, self.test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preference_not_obj(self):
        """Test that auth'ed user cannot create a prefs with not a JSON object."""
        client = APIClient()
        url = reverse("preferences-list")
        self.test_data["preference"] = "not a dictionary"
        # create a pref
        response = client.post(url, self.test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preference_duplicate(self):
        """Test that auth'ed user can not set duplicate prefs."""
        client = APIClient()
        url = reverse("preferences-list")

        # create a pref
        response = client.post(url, self.test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # create the pref a second time.
        dupe_data = self.test_data
        dupe_data["preference"] = {"test-pref": ["some", "other", "data"]}

        dupe_response = client.post(url, dupe_data, format="json", **self.headers)
        self.assertEqual(dupe_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_preference_auth(self):
        """Test that auth'ed user can delete their prefs."""
        pref = UserPreference.objects.filter(user=self.user).first()

        client = APIClient()
        url = reverse("preferences-detail", kwargs={"uuid": pref.uuid})

        # delete a pref
        response = client.delete(url, pref.preference, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # validate the pref isn't listed
        url = reverse("preferences-list")
        response = client.get(url, **self.headers)
        results = response.json().get("data")
        results_prefs = [r["preference"] for r in results]
        self.assertNotIn(pref.preference, results_prefs)

    def test_delete_preference_auth_other(self):
        """Test that an authed non-owner cannot delete unowned preferences."""
        a_user_dict = self._create_user_data()
        request_context = self._create_request_context(self.customer_data, a_user_dict, False)
        serializer = UserSerializer(data=a_user_dict, context=request_context)
        if serializer.is_valid(raise_exception=True):
            other_user = serializer.save()

        a_pref_id = UserPreference.objects.filter(user=other_user).first().uuid

        client = APIClient()
        url = reverse("preferences-detail", kwargs={"uuid": a_pref_id})
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_preference_auth(self):
        """Test that auth'ed user can update their prefs."""
        pref = UserPreference.objects.filter(user=self.user).first()

        client = APIClient()
        url = reverse("preferences-detail", kwargs={"uuid": pref.uuid})

        self.assertNotEqual(self.test_data["name"], pref.name)
        self.assertNotEqual(self.test_data["preference"], pref.preference)

        # update a pref
        response = client.put(url, self.test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # validate the pref is updated
        response = client.get(url, **self.headers)
        self.assertEqual(self.test_data["name"], response.data["name"])
        self.assertEqual(self.test_data["preference"], response.data["preference"])
