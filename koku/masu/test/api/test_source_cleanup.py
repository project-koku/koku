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
from unittest.mock import patch

from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from sources.config import Config
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient


@override_settings(ROOT_URLCONF="masu.urls")
class SourceCleanupTests(IamTestCase):
    """Test Cases for the source_cleanup endpoint."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    def _create_source_for_providers(self):
        """Helper to create a source for each test provider."""
        providers = Provider.objects.all()
        source_id = 1
        for provider in providers:
            source_def = {
                "source_id": source_id,
                "koku_uuid": provider.uuid,
                "name": provider.name,
                "source_type": provider.type,
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "acct10001",
                "offset": source_id + 1,
            }
            source = Sources(**source_def)
            source.save()
            source_id = source_id + 1

    def _create_out_of_order_delete_sources(self):
        """Helper to create out of order delete source for each test provider."""
        providers = Provider.objects.all()
        source_id = 1
        for provider in providers:
            source_def = {
                "source_id": source_id,
                "out_of_order_delete": True,
                "name": provider.name,
                "source_type": provider.type,
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "acct10001",
                "offset": source_id + 1,
            }
            source = Sources(**source_def)
            source.save()
            source_id = source_id + 1

    @patch("koku.middleware.MASU", return_value=True)
    def test_cleanup_all_good(self, _):
        """Test cleanup API when there are all healthy sources."""
        params = {}

        self._create_source_for_providers()
        with patch.object(SourcesHTTPClient, "get_source_details"):
            response = self.client.get(reverse("cleanup"), params)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("koku.middleware.MASU", return_value=True)
    def test_cleanup_missing_sources(self, _):
        """Test cleanup API when sources are missing on the platform."""
        params = {"missing_sources": ""}
        self._create_source_for_providers()

        sources = Sources.objects.all()
        expected_missing_list = []
        for source in sources:
            expected_missing_list.append(f"Source ID: {source.source_id})")

        self._create_source_for_providers()
        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.get(reverse("cleanup"), params)
            body = response.json()
            self.assertEqual(body.get("missing_sources"), expected_missing_list)

    @patch("koku.middleware.MASU", return_value=True)
    def test_cleanup_providers_without_sources(self, _):
        """Test cleanup API when providers are left over."""
        params = {"providers_without_sources": ""}

        providers = Provider.objects.all()
        expected_missing_list = []
        for provider in providers:
            expected_missing_list.append(f"{provider.name} ({provider.uuid})")

        response = self.client.get(reverse("cleanup"), params)
        body = response.json()

        self.assertEqual(body.get("providers_without_sources"), expected_missing_list)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_providers_without_sources(self, _):
        """Test to remove providers without sources."""
        params = {"providers_without_sources": ""}

        providers = Provider.objects.all()
        expected_missing_list = []
        for provider in providers:
            expected_missing_list.append(f"{provider.name} ({provider.uuid})")

        response = self.client.delete(f"{reverse('cleanup')}?providers_without_sources", params)
        body = response.json()
        self.assertEqual(body.get("job_queued"), "providers_without_sources")
        self.assertEqual(len(Provider.objects.all()), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_missing_sources(self, _):
        """Test cleanup API when deleting sources that are missing on the platform."""
        params = {"missing_sources": ""}
        self._create_source_for_providers()

        sources = Sources.objects.all()
        expected_missing_list = []
        for source in sources:
            expected_missing_list.append(f"Source ID: {source.source_id})")

        self._create_source_for_providers()
        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.delete(f"{reverse('cleanup')}?missing_sources", params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(Sources.objects.all()), 0)

        # Now run again with providers_without_sources parameter to remove providers.

        providers = Provider.objects.all()
        expected_provider_missing_list = []
        for provider in providers:
            expected_provider_missing_list.append(f"{provider.name} ({provider.uuid})")

        params = {"providers_without_sources": ""}
        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.delete(f"{reverse('cleanup')}?providers_without_sources", params)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(Provider.objects.all()), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_out_of_order_delete_sources(self, _):
        """Test to remove out of order delete sources."""
        params = {}
        self._create_out_of_order_delete_sources()

        providers = Provider.objects.all()
        expected_missing_provider_list = []
        for provider in providers:
            expected_missing_provider_list.append(f"{provider.name} ({provider.uuid})")

        sources = Sources.objects.all()
        expected_missing_list = []
        for source in sources:
            expected_missing_list.append(f"Source ID: {source.source_id})")

        with patch.object(SourcesHTTPClient, "get_source_details"):
            response = self.client.delete(f"{reverse('cleanup')}?out_of_order_deletes", params)
            body = response.json()
            self.assertEqual(body.get("job_queued"), "out_of_order_deletes")
            self.assertEqual(len(Sources.objects.all()), 0)
