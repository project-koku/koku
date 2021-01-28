#
# Copyright 2021 Red Hat, Inc.
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
"""Test the souce_cleanup endpoint view."""
import datetime
from django.test import RequestFactory
from unittest.mock import patch
from urllib.parse import urlencode
from api.provider.models import Provider
from api.provider.models import Sources
from rest_framework.test import APIClient
from api.iam.test.iam_test_case import IamTestCase
from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider


@override_settings(ROOT_URLCONF="masu.urls")
class SourceCleanupTests(IamTestCase):
    """Test Cases for the source_cleanup endpoint."""
    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_cleanup_all_good(self):
        """Test cleanup API when there are all healthy sources."""
        params = {}

        response = self.client.get(reverse("cleanup"), params)
        import pdb; pdb.set_trace()
        body = response.json()