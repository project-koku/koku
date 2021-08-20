#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
        for source_id, provider in enumerate(providers, start=1):
            source_def = {
                "source_id": source_id,
                "koku_uuid": provider.uuid,
                "source_uuid": provider.uuid,
                "name": provider.name,
                "source_type": provider.type,
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "acct10001",
                "offset": source_id + 1,
            }
            source = Sources(**source_def)
            source.save()

    def _create_out_of_order_delete_sources(self):
        """Helper to create out of order delete source for each test provider."""
        providers = Provider.objects.all()
        for source_id, provider in enumerate(providers, start=1):
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
        expected_missing_list = [
            f"Source ID: {source.source_id} Source UUID: {source.source_uuid}" for source in sources
        ]

        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.get(reverse("cleanup"), params)
            body = response.json()
            self.assertEqual(body.get("missing_sources"), expected_missing_list)

    @patch("koku.middleware.MASU", return_value=True)
    def test_cleanup_out_of_order_deletes(self, _):
        """Test cleanup API when providers are left over."""
        params = {"out_of_order_deletes": ""}
        self._create_out_of_order_delete_sources()

        sources = Sources.objects.all()
        expected_missing_list = [f"Source ID: {source.source_id}" for source in sources]

        response = self.client.get(reverse("cleanup"), params)
        body = response.json()

        self.assertEqual(body.get("out_of_order_deletes"), expected_missing_list)

    @patch("koku.middleware.MASU", return_value=True)
    def test_cleanup_providers_without_sources(self, _):
        """Test cleanup API when providers are left over."""
        params = {"providers_without_sources": ""}

        providers = Provider.objects.all()
        expected_missing_list = [f"{provider.name} ({provider.uuid})" for provider in providers]

        response = self.client.get(reverse("cleanup"), params)
        body = response.json()

        self.assertEqual(body.get("providers_without_sources"), expected_missing_list)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_providers_without_sources(self, _):
        """Test to remove providers without sources."""
        params = {"providers_without_sources": ""}
        response = self.client.delete(f"{reverse('cleanup')}?providers_without_sources", params)
        body = response.json()
        self.assertEqual(body.get("job_queued"), "providers_without_sources")
        self.assertEqual(len(Provider.objects.all()), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_specific_provider_without_sources(self, _):
        """Test to remove a specific provider without sources."""
        initial_count = len(Provider.objects.all())
        provider_uuid = str(Provider.objects.first().uuid)

        url_w_params = reverse("cleanup") + f"?providers_without_sources&uuid={provider_uuid}"
        response = self.client.delete(url_w_params)
        body = response.json()
        self.assertEqual(body.get("job_queued"), "providers_without_sources")
        self.assertEqual(len(Provider.objects.all()), initial_count - 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_invalid_uuid(self, _):
        """Test to remove a an invalid source_uuid."""
        url_w_params = reverse("cleanup") + "?providers_without_sources&uuid=abc"
        response = self.client.delete(url_w_params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_missing_sources(self, _):
        """Test cleanup API when deleting sources that are missing on the platform."""
        params = {"missing_sources": ""}
        self._create_source_for_providers()

        # assert that the test has sources and providers:
        self.assertNotEqual(len(Sources.objects.all()), 0)
        self.assertNotEqual(len(Provider.objects.all()), 0)

        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.delete(f"{reverse('cleanup')}?missing_sources", params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(Sources.objects.all()), 0)

        # Now run again with providers_without_sources parameter to remove providers.
        params = {"providers_without_sources": ""}
        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.delete(f"{reverse('cleanup')}?providers_without_sources", params)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(Provider.objects.all()), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_specific_missing_source(self, _):
        """Test cleanup API when deleting a specific source that is missing on the platform."""
        self._create_source_for_providers()
        initial_count = len(Sources.objects.all())
        self.assertNotEqual(initial_count, 0)
        source_uuid = str(Sources.objects.first().source_uuid)
        url_w_params = reverse("cleanup") + f"?missing_sources&uuid={source_uuid}"
        with patch.object(SourcesHTTPClient, "get_source_details", side_effect=SourceNotFoundError):
            response = self.client.delete(url_w_params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(Sources.objects.all()), initial_count - 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("koku.middleware.MASU", return_value=True)
    def test_delete_out_of_order_delete_sources(self, _):
        """Test to remove out of order delete sources."""
        params = {}
        self._create_out_of_order_delete_sources()
        self.assertNotEqual(len(Sources.objects.all()), 0)

        with patch.object(SourcesHTTPClient, "get_source_details"):
            response = self.client.delete(f"{reverse('cleanup')}?out_of_order_deletes", params)
            body = response.json()
            self.assertEqual(body.get("job_queued"), "out_of_order_deletes")
            self.assertEqual(len(Sources.objects.all()), 0)
