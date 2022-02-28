#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
    test_filename = os.path.join(settings.BASE_DIR, "..", "docs/source/specs/openapi.json")
    return get_json(test_filename)


class OpenAPIViewTest(TestCase):
    """Tests the openapi view."""

    @patch("api.openapi.view.get_json", return_value=read_api_json())
    def test_openapi_endpoint(self, _):
        """Test the openapi endpoint returns HTTP_200_OK."""
        url = reverse("openapi")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("api.openapi.view.get_json", return_value=None)
    def test_openapi_endpoint_failure(self, mock_get_json):
        """Test the openapi endpoint fails with HTTP_404_NOT_FOUND."""
        url = reverse("openapi")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        mock_get_json.assert_called_once()

    def test_get_json(self):
        """Test the get_json method can read a JSON file."""
        test_file_name = None
        with NamedTemporaryFile(mode="w", delete=False) as test_file:
            json_data = [1, 2, 3, 4, {"foo": "bar"}]
            json.dump(json_data, test_file)
            test_file_name = test_file.name
        result = get_json(test_file_name)
        self.assertEqual(result, json_data)
