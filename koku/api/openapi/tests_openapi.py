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
import gzip
import json
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from api.openapi.view import get_api_json


def get_api_json_error(path):
    """Raise error for mocked response."""
    raise FileNotFoundError()


class OpenAPIViewTest(TestCase):
    """Tests the openapi view."""

    @patch('api.openapi.view.get_api_json', return_value=json.dumps({}))
    def test_openapi_endpoint(self, mock_get_json):
        """Test the openapi endpoint."""
        url = reverse('openapi')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_json.assert_called_once()

    @patch('api.openapi.view.get_api_json', side_effect=get_api_json_error)
    def test_openapi_endpoint_failure(self, mock_get_json):
        """Test the openapi endpoint."""
        url = reverse('openapi')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        mock_get_json.assert_called_once()

    def test_get_api_json(self):
        """Test the get_api_json method."""
        test_file = NamedTemporaryFile(delete=False)
        json_data = {'foo': 'bar'}
        gzip_data = gzip.compress(json.dumps(json_data).encode())
        test_file.write(gzip_data)
        test_file.close()
        result = get_api_json(test_file.name)
        self.assertEqual(result, json_data)
