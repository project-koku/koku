#
# Copyright 2020 Red Hat, Inc.
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
"""Test the Report views."""
from uuid import uuid4

from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase


class TagsViewTest(IamTestCase):
    """Tests the report view."""

    TAGS = {
        # tags
        "aws-tags": "aws-tags-key",
        "azure-tags": "azure-tags-key",
        "openshift-tags": "openshift-tags-key",
        "openshift-aws-tags": "openshift-aws-tags-key",
        "openshift-azure-tags": "openshift-azure-tags-key",
        "openshift-all-tags": "openshift-all-tags-key",
    }

    def test_tags_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for tag_endpoint in self.TAGS.keys():
            with self.subTest(endpoint=tag_endpoint):
                url = reverse(tag_endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tags_key_endpoint_view_404(self):
        """Test tag key endpoint return 404 for not-real tags."""
        uuid = uuid4()
        for tag_endpoint in self.TAGS.values():
            with self.subTest(endpoint=tag_endpoint):
                url = reverse(tag_endpoint, args=[f"this-key-isn't-real-{str(uuid)}"])
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_tags_key_endpoint_view(self):
        """Test tag key endpoint return 200 and correct values for real tags."""
        for tag_endpoint, key_endpoint in self.TAGS.items():
            with self.subTest(endpoint=(tag_endpoint, key_endpoint)):
                url = reverse(tag_endpoint)
                response = self.client.get(url, **self.headers)
                data = response.data["data"][0]
                key, expected = data.get("key"), data.get("values")

                url = reverse(key_endpoint, args=[key])
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                values = response.data["data"]
                self.assertListEqual(values, expected)

    def test_invalid_key_only(self):
        """Test tag key endpoint returns 400 for key_only query."""
        for tag_endpoint, key_endpoint in self.TAGS.items():
            with self.subTest(endpoint=tag_endpoint):
                url = reverse(tag_endpoint)
                response = self.client.get(url, **self.headers)
                data = response.data["data"][0]
                key = data.get("key")

                url = reverse(key_endpoint, args=[key])
                response = self.client.get(url + "?key_only=True", **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
