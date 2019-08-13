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

"""Test the download endpoint view."""
import os
from unittest.mock import patch

from django.urls import reverse
from django.test import TestCase
from django.test.utils import override_settings

from celery.result import AsyncResult
from api.iam.models import Tenant

from masu.test import MasuTestCase

@override_settings(ROOT_URLCONF='masu.urls')
class DownloadAPIViewTest(TestCase):
    """Test Cases for the Download API."""
    def setUp(self):
        """Create test case setup."""
        super().setUp()
        Tenant.objects.get_or_create(schema_name='public')

    @patch(
        'masu.celery.tasks.check_report_updates.delay',
        return_value=AsyncResult('dc350f15-ffc7-4fcb-92d7-2a9f1275568e'),
    )
    def test_download(self, file_list):
        """Test the download endpoint."""
        url = reverse('report_download')
        response = self.client.get(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn('Download Request Task ID', body)
