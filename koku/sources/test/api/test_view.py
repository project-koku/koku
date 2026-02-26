#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the sources view."""
import json
import unittest
from random import randint
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

import requests_mock
from django.conf import settings
from django.core.cache import cache
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import viewsets
from rest_framework.response import Response

from api.common.permissions import RESOURCE_TYPE_MAP
from api.common.permissions.aws_access import AwsAccessPermission
from api.iam.models import Customer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from koku.middleware import IdentityHeaderMiddleware
from sources.api.source_type_mapping import PROVIDER_TYPE_TO_CMMO_ID
from sources.api.view import DestroySourceMixin
from sources.api.view import SourceFilter
from sources.api.view import SourcesViewSet


@override_settings(ROOT_URLCONF="sources.urls")
class SourcesViewTests(IamTestCase):
    """Test Cases for the sources endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.test_account = "10001"
        self.test_org_id = "1234567"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account, org_id=self.test_org_id)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        self.test_source_id = 1
        name = "Test Azure Source"
        customer_obj = Customer.objects.get(org_id=customer.get("org_id"))
        self.azure_provider = Provider(name=name, type=Provider.PROVIDER_AZURE, customer=customer_obj)
        self.azure_provider.save()

        self.azure_obj = Sources(
            source_id=self.test_source_id,
            auth_header=self.request_context["request"].META,
            account_id=customer.get("account_id"),
            org_id=customer.get("org_id"),
            offset=1,
            source_type=Provider.PROVIDER_AZURE,
            name=name,
            authentication={
                "credentials": {"client_id": "test_client", "tenant_id": "test_tenant", "client_secret": "test_secret"}
            },
            source_uuid=self.azure_provider.uuid,
        )
        self.azure_obj.save()

        mock_url = PropertyMock(return_value="http://www.sourcesclient.com/api/v1/sources/")
        SourcesViewSet.url = mock_url

    @unittest.skipIf(
        settings.ONPREM or settings.DEVELOPMENT,
        "SaaS-only: PATCH is allowed when ONPREM or DEVELOPMENT is True",
    )
    def test_source_patch(self):
        """Test the PATCH endpoint."""
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.patch(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                json={"credentials": credentials},
            )

            params = '{"credentials: blah}'
            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.patch(
                url, params, content_type="application/json", **self.request_context["request"].META
            )

            self.assertEqual(response.status_code, 405)

    @unittest.skipIf(
        settings.ONPREM or settings.DEVELOPMENT,
        "SaaS-only: PUT is allowed when ONPREM or DEVELOPMENT is True",
    )
    def test_source_put(self):
        """Test the PUT endpoint."""
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.put(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                json={"credentials": credentials},
            )

            params = {"credentials": credentials}
            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.put(
                url, json.dumps(params), content_type="application/json", **self.request_context["request"].META
            )

            self.assertEqual(response.status_code, 405)

    def test_source_list(self):
        """Test the LIST endpoint."""
        with requests_mock.mock() as m:
            m.get("http://www.sourcesclient.com/api/v1/sources/", status_code=200)

            url = reverse("sources-list")

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get("meta").get("count"), 1)

    def test_aws_s3_regions(self):
        """Given a request for AWS S3 regions, a subset of all available regions should be returned"""
        all_regions = {
            "af-south-1",
            "ap-east-1",
            "ap-northeast-1",
            "ap-northeast-2",
            "ap-northeast-3",
            "ap-south-1",
            "ap-south-2",
            "ap-southeast-1",
            "ap-southeast-2",
            "ap-southeast-3",
            "ap-southeast-4",
            "ca-central-1",
            "eu-central-1",
            "eu-central-2",
            "eu-north-1",
            "eu-south-1",
            "eu-south-2",
            "eu-west-1",
            "eu-west-2",
            "eu-west-3",
            "me-central-1",
            "me-south-1",
            "sa-east-1",
            "us-east-1",
            "us-east-2",
            "us-west-1",
            "us-west-2",
        }

        response = self.client.get(
            reverse("sources-aws-s3-regions"), {"limit": 1000}, **self.request_context["request"].META
        )
        regions = response.json()["data"]

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(all_regions, set(regions))
        self.assertTrue(all_regions.issubset(set(regions)))

    def test_aws_s3_regions_pagination(self):
        """Test that the API response is paginated"""
        limit = 4

        response = self.client.get(
            reverse("sources-aws-s3-regions"),
            {"limit": limit},
            **self.request_context["request"].META,
        )
        regions = response.json()["data"]

        self.assertEqual(len(regions), limit)

    def test_source_list_other_header(self):
        """Test the LIST endpoint with other auth header not matching test data."""
        user_data = self._create_user_data()
        other_account = "10002"
        other_org_id = "2222222"
        customer = self._create_customer_data(account=other_account, org_id=other_org_id)
        IdentityHeaderMiddleware.create_customer(other_account, other_org_id, "POST")
        request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

        with requests_mock.mock() as m:
            m.get("http://www.sourcesclient.com/api/v1/sources/", status_code=200)

            url = reverse("sources-list")

            response = self.client.get(url, content_type="application/json", **request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get("meta").get("count"), 0)

    def test_source_get(self):
        """Test the GET endpoint."""
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(body)

    def test_source_get_other_header(self):
        """Test the GET endpoint other header not matching test data."""
        user_data = self._create_user_data()
        other_account = "10002"
        other_org_id = "2222222"
        customer = self._create_customer_data(account=other_account, org_id=other_org_id)
        IdentityHeaderMiddleware.create_customer(other_account, other_org_id, "POST")

        request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.get(url, content_type="application/json", **request_context["request"].META)
            self.assertEqual(response.status_code, 404)

    @unittest.skipIf(
        settings.ONPREM or settings.DEVELOPMENT,
        "SaaS-only: DELETE is allowed when ONPREM or DEVELOPMENT is True",
    )
    def test_source_destroy_not_allowed(self):
        """Test access to the destroy endpoint."""
        url = reverse("sources-detail", kwargs={"pk": self.test_source_id})
        response = self.client.delete(url, content_type="application/json", **self.request_context["request"].META)
        self.assertEqual(response.status_code, 405)

    @patch("sources.api.view.ProviderManager.provider_statistics", return_value={})
    def test_source_get_stats(self, _):
        """Test the GET status endpoint."""
        url = reverse("sources-stats", kwargs={"pk": self.test_source_id})
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)

    @patch("sources.api.view.ProviderManager", side_effect=ProviderManagerError("test error"))
    def test_source_list_zerror(self, _):
        """Test provider_linked is False in list when Provider does not exist."""
        cache.clear()
        url = reverse("sources-list")
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertTrue(body.get("data"))
        self.assertFalse(body.get("data")[0]["provider_linked"])

    @patch("sources.api.view.ProviderManager")
    def test_source_list_provider_success(self, mock_provider_manager):
        """Test provider_linked is True in list when Provider exists."""
        provider_manager = ProviderManager(self.azure_provider.uuid)
        mock_provider_manager.return_value = provider_manager
        url = reverse("sources-list")
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertTrue(body.get("data"))
        self.assertTrue(body.get("data")[0]["provider_linked"])
        self.assertTrue(body.get("data")[0]["active"])

    @patch("sources.api.view.ProviderManager", side_effect=ProviderManagerError("test error"))
    def test_source_retrieve_error(self, _):
        """Test provider_linked is False in Source when Provider does not exist."""
        url = reverse("sources-detail", kwargs={"pk": self.test_source_id})
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertFalse(body["provider_linked"])
        self.assertFalse(body["active"])

    @patch("sources.api.view.ProviderManager", side_effect=ProviderManagerError("test error"))
    def test_source_get_stats_error(self, _):
        """Test provider_linked is False in source-stats when Provider does not exist."""
        url = reverse("sources-stats", kwargs={"pk": self.test_source_id})
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertFalse(body["provider_linked"])

    def test_source_get_random_int(self):
        """Test the GET endpoint with non-existent source int id."""
        source_id = randint(20, 100)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{source_id}/",
                status_code=404,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": source_id})

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 404)
            self.assertIsNotNone(body)

    def test_source_get_random_uuid(self):
        """Test the GET endpoint with non-existent source uuid."""
        source_id = uuid4()

        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{source_id}/",
                status_code=404,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": source_id})

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 404)
            self.assertIsNotNone(body)

    def test_sources_access(self):
        """Test the limiting of source type visibility."""
        mock_user = Mock(admin=True)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        self.assertEqual(excluded, [])

        mock_user = Mock(admin=False, access=None)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        expected = []
        for resource_type in RESOURCE_TYPE_MAP.keys():
            expected.extend(RESOURCE_TYPE_MAP.get(resource_type))
        self.assertEqual(sorted(list(set(excluded))), sorted(list(set(expected))))

        permissions = {AwsAccessPermission.resource_type: {"read": []}}
        mock_user = Mock(admin=False, access=permissions)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        expected = []
        for resource_type in RESOURCE_TYPE_MAP.keys():
            expected.extend(RESOURCE_TYPE_MAP.get(resource_type))
        self.assertEqual(sorted(list(set(excluded))), sorted(list(set(expected))))

        permissions = {AwsAccessPermission.resource_type: {"read": ["*"]}}
        mock_user = Mock(admin=False, access=permissions)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        expected = [
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_AZURE_LOCAL,
            Provider.PROVIDER_OCP,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_GCP_LOCAL,
        ]
        self.assertEqual(sorted(list(set(excluded))), sorted(list(set(expected))))


@override_settings(ROOT_URLCONF="sources.urls")
class SourceFilterTests(IamTestCase):
    """Test Cases for SourceFilter custom filters."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.test_account = "10001"
        self.test_org_id = "1234567"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account, org_id=self.test_org_id)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        customer_obj = Customer.objects.get(org_id=customer.get("org_id"))

        # Create an OCP source with cluster_id
        self.ocp_provider = Provider(name="Test OCP", type=Provider.PROVIDER_OCP, customer=customer_obj)
        self.ocp_provider.save()
        self.ocp_source = Sources(
            source_id=10,
            auth_header=self.request_context["request"].META,
            account_id=customer.get("account_id"),
            org_id=customer.get("org_id"),
            offset=10,
            source_type=Provider.PROVIDER_OCP,
            name="Test OCP Source",
            authentication={"credentials": {"cluster_id": "test-cluster-abc"}},
            source_uuid=self.ocp_provider.uuid,
        )
        self.ocp_source.save()

        # Create an Azure source
        self.azure_provider = Provider(name="Test Azure", type=Provider.PROVIDER_AZURE, customer=customer_obj)
        self.azure_provider.save()
        self.azure_source = Sources(
            source_id=11,
            auth_header=self.request_context["request"].META,
            account_id=customer.get("account_id"),
            org_id=customer.get("org_id"),
            offset=11,
            source_type=Provider.PROVIDER_AZURE,
            name="Test Azure Source",
            authentication={"credentials": {"client_id": "test_client"}},
            source_uuid=self.azure_provider.uuid,
        )
        self.azure_source.save()

        mock_url = PropertyMock(return_value="http://www.sourcesclient.com/api/v1/sources/")
        SourcesViewSet.url = mock_url

    def test_filter_by_source_type_id_ocp(self):
        """Test filtering sources by source_type_id for OCP."""
        cache.clear()
        url = reverse("sources-list")
        response = self.client.get(
            url,
            {"source_type_id": PROVIDER_TYPE_TO_CMMO_ID[Provider.PROVIDER_OCP]},
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        for source in body["data"]:
            self.assertEqual(source["source_type"], Provider.PROVIDER_OCP)

    def test_filter_by_source_type_id_azure(self):
        """Test filtering sources by source_type_id for Azure."""
        cache.clear()
        url = reverse("sources-list")
        response = self.client.get(
            url,
            {"source_type_id": PROVIDER_TYPE_TO_CMMO_ID[Provider.PROVIDER_AZURE]},
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        for source in body["data"]:
            self.assertEqual(source["source_type"], Provider.PROVIDER_AZURE)

    def test_filter_by_source_type_id_invalid(self):
        """Test filtering sources by invalid source_type_id returns empty."""
        cache.clear()
        url = reverse("sources-list")
        response = self.client.get(
            url,
            {"source_type_id": "999"},
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["meta"]["count"], 0)

    def test_filter_by_source_ref(self):
        """Test filtering sources by source_ref (cluster_id)."""
        cache.clear()
        url = reverse("sources-list")
        response = self.client.get(
            url,
            {"source_ref": "test-cluster-abc"},
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(body["data"][0]["source_type"], Provider.PROVIDER_OCP)

    def test_filter_by_source_ref_no_match(self):
        """Test filtering sources by source_ref with no match."""
        cache.clear()
        url = reverse("sources-list")
        response = self.client.get(
            url,
            {"source_ref": "nonexistent-cluster"},
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["meta"]["count"], 0)

    def test_filter_by_source_type_id_unit(self):
        """Test SourceFilter.filter_by_source_type_id directly."""
        queryset = Sources.objects.all()
        source_filter = SourceFilter()
        # Valid source_type_id
        filtered = source_filter.filter_by_source_type_id(queryset, "source_type_id", "1")
        for source in filtered:
            self.assertEqual(source.source_type, Provider.PROVIDER_OCP)

        # Invalid source_type_id returns empty
        filtered = source_filter.filter_by_source_type_id(queryset, "source_type_id", "999")
        self.assertEqual(filtered.count(), 0)

    def test_filter_by_source_ref_unit(self):
        """Test SourceFilter.filter_by_source_ref directly."""
        queryset = Sources.objects.all()
        source_filter = SourceFilter()
        filtered = source_filter.filter_by_source_ref(queryset, "source_ref", "test-cluster-abc")
        self.assertTrue(filtered.exists())
        for source in filtered:
            self.assertEqual(
                source.authentication.get("credentials", {}).get("cluster_id"),
                "test-cluster-abc",
            )


@override_settings(ROOT_URLCONF="sources.urls")
class SourcesViewCreateTests(IamTestCase):
    """Test Cases for the SourcesViewSet.create method."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.test_account = "10001"
        self.test_org_id = "1234567"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account, org_id=self.test_org_id)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

    @patch("sources.api.view.invalidate_cache_for_tenant_and_cache_key")
    def test_create_method_success(self, mock_invalidate):
        """Test the create method calls super and invalidates cache."""
        viewset = SourcesViewSet()
        mock_request = Mock()
        mock_request.user.customer.schema_name = "test_schema"

        # Mock create on GenericViewSet (which IS in the MRO) since CreateModelMixin
        # is only added when DEVELOPMENT or ONPREM is True (not the case in tox).
        with patch.object(viewsets.GenericViewSet, "create", create=True, return_value=Response(status=201)):
            result = viewset.create(request=mock_request)
            self.assertEqual(result.status_code, 201)
            mock_invalidate.assert_called_once()

    @patch("sources.api.view.invalidate_cache_for_tenant_and_cache_key")
    def test_create_method_storage_error(self, mock_invalidate):
        """Test the create method raises SourcesException on SourcesStorageError."""
        from sources.api.view import SourcesException
        from sources.storage import SourcesStorageError

        viewset = SourcesViewSet()
        mock_request = Mock()
        mock_request.user.customer.schema_name = "test_schema"

        with patch.object(
            viewsets.GenericViewSet, "create", create=True, side_effect=SourcesStorageError("test error")
        ):
            with self.assertRaises(SourcesException):
                viewset.create(request=mock_request)

    @patch("sources.api.view.invalidate_cache_for_tenant_and_cache_key")
    def test_create_method_dependency_error(self, mock_invalidate):
        """Test the create method raises SourcesDependencyException on SourcesDependencyError."""
        from sources.api.serializers import SourcesDependencyError
        from sources.api.view import SourcesDependencyException

        viewset = SourcesViewSet()
        mock_request = Mock()
        mock_request.user.customer.schema_name = "test_schema"

        with patch.object(
            viewsets.GenericViewSet, "create", create=True, side_effect=SourcesDependencyError("dep error")
        ):
            with self.assertRaises(SourcesDependencyException):
                viewset.create(request=mock_request)


class DestroySourceMixinTests(IamTestCase):
    """Test Cases for the DestroySourceMixin.destroy with ONPREM publish."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.test_account = "10001"
        self.test_org_id = "1234567"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account, org_id=self.test_org_id)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        customer_obj = Customer.objects.get(org_id=customer.get("org_id"))

        self.provider = Provider(name="Test OCP", type=Provider.PROVIDER_OCP, customer=customer_obj)
        self.provider.save()
        self.source = Sources(
            source_id=20,
            auth_header=self.request_context["request"].META,
            account_id=customer.get("account_id"),
            org_id=customer.get("org_id"),
            offset=20,
            source_type=Provider.PROVIDER_OCP,
            name="Test OCP Source",
            authentication={"credentials": {"cluster_id": "destroy-test-cluster"}},
            source_uuid=self.provider.uuid,
            koku_uuid=self.provider.uuid,
        )
        self.source.save()

    @patch("sources.api.view.publish_application_destroy_event")
    @patch("sources.api.view.invalidate_cache_for_tenant_and_cache_key")
    @override_settings(ONPREM=True)
    def test_destroy_publishes_kafka_event_when_onprem(self, mock_invalidate, mock_publish):
        """Test that destroy publishes Kafka event when ONPREM is True."""
        mock_request = Mock()
        mock_request.user.customer.schema_name = "test_schema"
        mock_request.user.customer.account_id = self.test_account
        mock_request.user.customer.org_id = self.test_org_id
        mock_request.user.identity_header = {"encoded": "test-header"}

        class TestDestroyView(DestroySourceMixin):
            def get_object(self):
                return self.source

        view = TestDestroyView()
        view.source = self.source

        with (
            patch.object(view, "get_object", return_value=self.source),
            patch("sources.api.view.ProviderBuilder") as mock_builder,
            patch("rest_framework.mixins.DestroyModelMixin.destroy", return_value=Response(status=204)),
        ):
            mock_builder.return_value.destroy_provider.return_value = None
            DestroySourceMixin.destroy(view, request=mock_request)

            mock_publish.assert_called_once_with(self.source)

    @patch("sources.api.view.publish_application_destroy_event")
    @patch("sources.api.view.invalidate_cache_for_tenant_and_cache_key")
    @override_settings(ONPREM=False)
    def test_destroy_skips_kafka_event_when_not_onprem(self, mock_invalidate, mock_publish):
        """Test that destroy does NOT publish Kafka event when ONPREM is False."""
        mock_request = Mock()
        mock_request.user.customer.schema_name = "test_schema"
        mock_request.user.customer.account_id = self.test_account
        mock_request.user.customer.org_id = self.test_org_id
        mock_request.user.identity_header = {"encoded": "test-header"}

        class TestDestroyView(DestroySourceMixin):
            def get_object(self):
                return None

        view = TestDestroyView()

        with (
            patch.object(view, "get_object", return_value=self.source),
            patch("sources.api.view.ProviderBuilder") as mock_builder,
            patch("rest_framework.mixins.DestroyModelMixin.destroy", return_value=Response(status=204)),
        ):
            mock_builder.return_value.destroy_provider.return_value = None
            DestroySourceMixin.destroy(view, request=mock_request)

            mock_publish.assert_not_called()
