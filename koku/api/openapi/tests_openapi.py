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
"""Test the Open API endpoint."""
import json
import os
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from api.openapi.view import get_json
from koku import settings


def read_api_json():
    """Read the openapi.json file out of the docs dir."""
    test_filename = os.path.join(settings.BASE_DIR, '..',
                                 'docs/source/specs/openapi.json')
    return get_json(test_filename)


class OpenAPIViewTest(TestCase):
    """Tests the openapi view."""

    @patch('api.openapi.view.get_json', return_value=read_api_json())
    def test_openapi_endpoint(self, _):
        """Test the openapi endpoint returns HTTP_200_OK."""
        url = reverse('openapi')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('api.openapi.view.get_json', return_value=None)
    def test_openapi_endpoint_failure(self, mock_get_json):
        """Test the openapi endpoint fails with HTTP_404_NOT_FOUND."""
        url = reverse('openapi')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        mock_get_json.assert_called_once()

    def test_get_json(self):
        """Test the get_json method can read a JSON file."""
        test_file_name = None
        with NamedTemporaryFile(mode='w', delete=False) as test_file:
            json_data = [1, 2, 3, 4, {'foo': 'bar'}]
            json.dump(json_data, test_file)
            test_file_name = test_file.name
        result = get_json(test_file_name)
        self.assertEqual(result, json_data)
