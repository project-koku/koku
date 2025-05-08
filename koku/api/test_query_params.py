#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the QueryParameters."""
import random
from collections import OrderedDict
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.test import TestCase
from faker import Faker
from querystring_parser import parser
from rest_framework.serializers import ValidationError

from api.models import Provider
from api.models import Tenant
from api.models import User
from api.query_params import get_tenant
from api.query_params import QueryParameters
from api.report.serializers import ParamSerializer
from api.report.view import ReportView

PROVIDERS = [
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_OCP,
    Provider.PROVIDER_GCP,
    Provider.OCP_AWS,
    Provider.OCP_AZURE,
    Provider.OCP_ALL,
]
ACCESS_KEYS = {
    Provider.PROVIDER_AWS.lower(): ["aws.account", "aws.organizational_unit"],
    Provider.PROVIDER_GCP.lower(): ["gcp.account", "gcp.project"],
    Provider.PROVIDER_AZURE.lower(): ["azure.subscription_guid"],
    Provider.PROVIDER_OCP.lower(): ["openshift.cluster", "openshift.project", "openshift.node"],
    Provider.OCP_AWS.lower(): [
        "aws.account",
        "aws.organizational_unit",
        "openshift.cluster",
        "openshift.project",
        "openshift.node",
    ],
    Provider.OCP_AZURE.lower(): [
        "azure.subscription_guid",
        "openshift.cluster",
        "openshift.project",
        "openshift.node",
    ],
    Provider.OCP_ALL.lower(): [
        "aws.account",
        "aws.organizational_unit",
        "azure.subscription_guid",
        "gcp.account",
        "gcp.project",
        "openshift.cluster",
        "openshift.project",
        "openshift.node",
    ],
}


class QueryParametersTests(TestCase):
    """Unit tests for QueryParameters."""

    FAKE = Faker()

    def setUp(self):
        """Test setup."""
        self.fake_uri = (
            f"filter[resolution]={self.FAKE.word()}&"
            f"filter[time_scope_value]={random.randint(0, 9999)}&"
            f"filter[time_scope_units]={self.FAKE.word()}&"
            f"group_by[{self.FAKE.word()}]=*&"
            f"order_by[{self.FAKE.word()}]=asc"
        )
        self.provider = random.choice(PROVIDERS).lower()
        self.test_read_access = {random.choice(ACCESS_KEYS[self.provider]): {"read": ["*"]}}

    def test_constructor(self):
        """Test that constructor creates a QueryParameters object.

        This test is a bit fatter than it needs to be to help show how to mock
        out the Request and View objects.
        """
        tag_keys = ["app", "az", "environment", "cost_center", "fake", "other", "this"]
        fake_objects = Mock()
        fake_objects.objects.values_list.return_value.distinct.return_value = tag_keys
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=Mock(get=lambda key, default: default), customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=random.choice(PROVIDERS)),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        self.assertIsInstance(QueryParameters(fake_request, fake_view), QueryParameters)

    def test_constructor_invalid_uri(self):
        """Test that ValidationError is raised with an invalid uri."""
        fake_request = Mock(spec=HttpRequest, GET=Mock(urlencode=Mock(return_value=self.FAKE.paragraph())))
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.FAKE.word()),
            report="tags",
            serializer=Mock,
            tag_providers=[],
        )
        with self.assertRaises(ValidationError):
            QueryParameters(fake_request, fake_view)

    def test_constructor_invalid_data(self):
        """Test that ValidationError is raised when serializer data is invalid."""

        class MockSerializer(Mock):
            """Mock Serializer for testing validity."""

            def __init__(self, *args, **kwargs):
                """Constructor."""
                super().__init__(*args, spec=ParamSerializer, is_valid=lambda: False, **kwargs)

        fake_request = Mock(spec=HttpRequest, GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.FAKE.word()),
            report=self.FAKE.word(),
            serializer=MockSerializer,
            tag_providers=[],
        )
        with self.assertRaises(ValidationError):
            QueryParameters(fake_request, fake_view)

    def test_accept_type_property(self):
        """Test that the accept_type property returns expected value."""
        expected = self.FAKE.word()
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
            META=Mock(get=Mock(return_value=expected)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.accept_type, expected)

    def test_access_property(self):
        """Test that the access property returns expected value."""
        fake_request = Mock(
            spec=HttpRequest,
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.access, self.test_read_access)

    def test_delta_property(self):
        """Test that the delta property returns expected value."""
        expected = self.FAKE.word()
        fake_uri = f"delta={expected}"
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.delta, expected)

    def test_category_property(self):
        """Test that the category property returns expected value."""
        expected = self.FAKE.word()
        fake_uri = f"category={expected}"
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.category, expected)

    def test_tenant_property(self):
        """Test that the tenant property returns expected value."""
        expected = self.FAKE.word()
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with patch("api.query_params.get_tenant", return_value=expected):
            params = QueryParameters(fake_request, fake_view)
            self.assertEqual(params.tenant, expected)

    def test_parameters_property(self):
        """Test that the parameters property returns expected value."""
        expected = parser.parse(str(self.fake_uri))
        # add access since it is a part of the parameters but not the uri
        expected["access"] = OrderedDict()
        expected["exclude"] = OrderedDict()
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.parameters, expected)

    def test_parameters_property_setter(self):
        """Test that the parameters property setter works."""
        expected = self.FAKE.pydict()
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        params.parameters = expected
        self.assertEqual(params.parameters, expected)

    def test_url_data_property(self):
        """Test that the url_data property returns expected value."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.url_data, self.fake_uri)

    def test_user_property(self):
        """Test that the user property returns expected value."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertIsInstance(params.tenant, Tenant)

    def test_get_groupby_default(self):
        """Test that get_group_by() returns the provided default value."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertIsInstance(params.get("group_by"), dict)

    def test_get_set(self):
        """Test that set() assigns the provided value and get() retrieves it."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        key = self.FAKE.word()
        value = self.FAKE.word()
        params.set(key, value)
        self.assertEqual(params.get(key), value)

    def test_get_set_filter(self):
        """Test that set() assigns the provided value and get() retrieves it."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        key = self.FAKE.word()
        value = self.FAKE.word()
        params.set_filter(**{key: value})
        self.assertEqual(params.get_filter(key), value)

    def test_has_filter_no_filter(self):
        """Test the default filter query parameters."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter("time_scope_units"), "day")
        self.assertEqual(params.get_filter("time_scope_value"), "-10")
        self.assertEqual(params.get_filter("resolution"), "daily")

    def test_has_start_end_dates_filter_no_filter(self):
        """Test the default filter query parameters with start and end dates."""
        fake_uri = "start_date=2021-04-01&" "end_date=2021-04-13"
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertIsNone(params.get_filter("time_scope_units"))
        self.assertIsNone(params.get_filter("time_scope_value"))
        self.assertEqual(params.get_filter("resolution"), "daily")

    def test_has_filter_no_value(self):
        """Test the default filter parameters when time_scope_value is undefined."""
        fake_uri = "filter[resolution]=monthly&" "filter[time_scope_units]=month"
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter("time_scope_value"), "-1")

    def test_has_filter_no_units(self):
        """Test the default filter parameters when time_scope_units is undefined."""
        fake_uri = "filter[resolution]=monthly&" "filter[time_scope_value]=-1"
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter("time_scope_units"), "month")

    def test_has_filter_no_resolution(self):
        """Test the default filter parameters when resolution is undefined."""
        fake_uri = "filter[time_scope_units]=month&" "filter[time_scope_value]=-1"
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=self.provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter("resolution"), "monthly")

    def test_access_with_wildcard(self):
        """Test wildcard doesn't update query parameters."""
        provider = random.choice(PROVIDERS)
        fake_uri = "group_by[account]=*&" "group_by[region]=*"
        test_access = {f"{provider}.account": {"read": ["*"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=provider),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_group_by("account"), "*")
        self.assertEqual(params.get_group_by("region"), "*")

    def test_access_replace_wildcard(self):
        """Test that a group by account wildcard only has access to the proper accounts."""
        fake_uri = "group_by[account]=*&" "group_by[region]=*"
        test_access = {"aws.account": {"read": ["account1", "account2"]}, "aws.organizational_unit": {"read": ["*"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=Provider.PROVIDER_AWS),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_access("account"), ["account1", "account2"])
        self.assertEqual(params.get_group_by("region"), "*")

    def test_access_gb_filtered_intersection(self):
        """Test that a group by account filtered list causes a 403 when filtering on accounts without access."""
        guid1 = uuid4()
        guid2 = uuid4()
        guid3 = uuid4()
        fake_uri = (
            f"group_by[subscription_guid]={guid1}&"
            f"group_by[subscription_guid]={guid2}&"
            f"group_by[resource_location]=*"
        )
        test_access = {"azure.subscription_guid": {"read": [str(guid1), str(guid3)]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=Provider.PROVIDER_AZURE),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with self.assertRaises(PermissionDenied):
            QueryParameters(fake_request, fake_view)

    def test_access_empty_intersection(self):
        """Test that a group by cluster filtered list causes 403 with empty intersection."""
        fake_uri = "group_by[cluster]=cluster1&" "group_by[cluster]=cluster3"
        test_access = {"openshift.cluster": {"read": ["cluster4", "cluster2"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=Provider.PROVIDER_OCP),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with self.assertRaises(PermissionDenied):
            QueryParameters(fake_request, fake_view)

    def test_access_add_account_filter(self):
        """Test that if no group_by or filter is present a filter of accounts is added."""
        fake_uri = "filter[region]=*"
        test_access = {"aws.account": {"read": ["account1", "account2"]}, "aws.organizational_unit": {"read": ["*"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=Provider.PROVIDER_AWS),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_access("account"), ["account1", "account2"])
        self.assertEqual(params.get_filter("region"), "*")

    def test_update_query_parameters_add_subscription_guid_filter_obj(self):
        """Test that if no group_by or filter is present, access is the subscription_guids available."""
        guid1 = uuid4()
        guid2 = uuid4()
        test_access = {"azure.subscription_guid": {"read": [guid1, guid2]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=Provider.PROVIDER_AZURE),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_access("subscription_guid"), [guid1, guid2])

    def test_update_query_parameters_filtered_intersection(self):
        """Test that a filter by cluster filtered list causes a 403 when filtering on accounts without access."""
        fake_uri = "filter[cluster]=cluster1&" "filter[cluster]=cluster3"
        test_access = {"openshift.cluster": {"read": ["cluster1", "cluster2"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=test_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=Provider.PROVIDER_OCP),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with self.assertRaises(PermissionDenied):
            QueryParameters(fake_request, fake_view)

    def test_get_tenant(self):
        """Test that get_tenant() returns a Tenant."""
        user = Mock(customer=Mock(schema_name="org1234567"))
        self.assertIsInstance(get_tenant(user), Tenant)

    def test_get_tenant_invalid(self):
        """Test that get_tenant() raises ValidationError when user is invalid."""
        with self.assertRaises(ValidationError):
            get_tenant(None)

    def test_get_tenant_no_user(self):
        """Test that get_tenant() raises ValidationError when user is missing."""
        user = Mock(customer=Mock(schema_name="org1234567"))
        with patch("api.query_params.Tenant.objects.get", side_effect=User.DoesNotExist):
            with self.assertRaises(ValidationError):
                get_tenant(user)

    def test_process_tag_query_params(self):
        """Test that a list of tag keys is reduced to those queried."""
        fake_uri = (
            "filter[resolution]=monthly&"
            "filter[time_scope_value]=-1&"
            "filter[time_scope_units]=month&"
            "filter[tag:environment]=prod&"
            "group_by[tag:app]=*"
        )
        tag_keys = ["app", "az", "environment", "cost_center", "fake", "other", "this"]
        expected = {"tag:app", "tag:environment"}

        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=Mock(get=lambda key, default: default), customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_objects = Mock()
        fake_objects.objects.values_list.return_value.distinct.return_value = tag_keys
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=random.choice(PROVIDERS)),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=["fake"],
        )
        with patch("reporting.provider.all.models.EnabledTagKeys.objects") as mock_object:
            mock_object.filter.return_value.values_list.return_value.distinct.return_value = tag_keys
            params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.tag_keys, expected)

    def test_process_exclude_query_params(self):
        """Test that a exclude filter is handled depnedent on unleash settings."""
        fake_uri = (
            "filter[resolution]=monthly&"
            "filter[time_scope_value]=-1&"
            "filter[time_scope_units]=month&"
            "exclude[account]=prod&"
            "group_by[account]=*"
        )

        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=Mock(get=lambda key, default: default), customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value=fake_uri)),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=random.choice(PROVIDERS)),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.parameters.get("exclude"), {"account": "prod"})

    def test_get_providers(self):
        """Test get providers returns the correct access keys."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=Mock(get=lambda key, default: default), customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=random.choice(PROVIDERS)),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        for provider in PROVIDERS:
            provider = provider.lower()
            with self.subTest(provider=provider):
                temp = params._get_providers(provider)
                result = []
                for res in temp:
                    result.append(res[2])
                expected = ACCESS_KEYS[provider]
                self.assertEqual(sorted(result), sorted(expected))

    def test_get_providers_with_nonsense_provider(self):
        """Test get providers raises validation error with nonsense provider."""
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=Mock(get=lambda key, default: default), customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=self.FAKE.word(),
            query_handler=Mock(provider=random.choice(PROVIDERS)),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        with self.assertRaises(ValidationError):
            params._get_providers("nonsense")

    def test_partial_access_ocp_all_partial_aws(self):
        """Test set access returns account numbers."""
        self.test_read_access = {"aws.account": {"read": ["999999999"]}, "azure.subscription_guid": {"read": ["*"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.OCP_ALL,
            query_handler=Mock(provider=Provider.OCP_ALL),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with patch("reporting.models.OCPAllCostLineItemDailySummaryP.objects", return_value=[]):
            params = QueryParameters(fake_request, fake_view)
            self.assertEqual(params.get_filter("account"), ["999999999"])

    def test_partial_access_ocp_all_no_azure_access(self):
        """Test set access returns account numbers."""
        self.test_read_access = {"aws.account": {"read": ["999999999"]}, "azure.subscription_guid": {"read": []}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.OCP_ALL,
            query_handler=Mock(provider=Provider.OCP_ALL),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with patch("reporting.models.OCPAllCostLineItemDailySummaryP.objects", return_value=[]):
            params = QueryParameters(fake_request, fake_view)
            self.assertEqual(params.get_filter("account"), ["999999999"])

    def test_partial_access_ocp_all_partial_azure_access(self):
        """Test set access returns account numbers."""
        guid = uuid4()
        self.test_read_access = {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["*"]},
            "azure.subscription_guid": {"read": [str(guid)]},
        }
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.OCP_ALL,
            query_handler=Mock(provider=Provider.OCP_ALL),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with patch("reporting.models.OCPAllCostLineItemDailySummaryP.objects") as mock_object:
            mock_object.filter.return_value.values_list.return_value.distinct.return_value = ["999999999"]
            params = QueryParameters(fake_request, fake_view)
            self.assertEqual(sorted(params.get_filter("account")), sorted(["999999999", str(guid)]))

    def test_check_wildcard_access(self):
        """Test check restrictions returns False when all access is wildcard."""
        self.test_read_access = {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["*"]},
            "azure.subscription_guid": {"read": ["*"]},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": ["*"]},
        }
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.OCP_ALL,
            query_handler=Mock(provider=Provider.OCP_ALL),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        access_list = params._get_providers(Provider.OCP_ALL.lower())
        result = params._check_restrictions(access_list)
        self.assertFalse(result)

    def test_check_wildcard_access_with_restrictions(self):
        """Test check restrictions returns True when 1 provider is restricted."""
        self.test_read_access = {"aws.account": {"read": ["999999999"]}, "azure.subscription_guid": {"read": ["*"]}}
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.OCP_ALL,
            query_handler=Mock(provider=Provider.OCP_ALL),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        with patch("reporting.models.OCPAllCostLineItemDailySummaryP.objects", return_value=[]):
            params = QueryParameters(fake_request, fake_view)
            access_list = params._get_providers(Provider.OCP_ALL.lower())
            result = params._check_restrictions(access_list)
        self.assertTrue(result)

    def test_check_wildcard_access_with_ocp_restrictions(self):
        """Test check restrictions returns False when non-ocp have wildcard, but ocp is restricted."""
        self.test_read_access = {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["*"]},
            "azure.subscription_guid": {"read": ["*"]},
            "openshift.cluster": {"read": ["my-ocp-cluster"]},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": ["*"]},
        }
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.OCP_ALL,
            query_handler=Mock(provider=Provider.OCP_ALL),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        access_list = params._get_providers(Provider.OCP_ALL.lower())
        result = params._check_restrictions(access_list)
        self.assertFalse(result)

    def test_get_org_unit_account_hierarchy(self):
        """Test aws get org unit account hierarchy returns list of all accounts in org units tree."""
        self.test_read_access = {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["OU_001"]},
        }
        expected = ["999999991", "999999992", "999999995"]
        fake_request = Mock(
            spec=HttpRequest,
            user=Mock(access=self.test_read_access, customer=Mock(schema_name="org1234567")),
            GET=Mock(urlencode=Mock(return_value="")),
        )
        fake_view = Mock(
            spec=ReportView,
            provider=Provider.PROVIDER_AWS,
            query_handler=Mock(provider=Provider.PROVIDER_AWS),
            report=self.FAKE.word(),
            serializer=Mock,
            tag_providers=[],
        )
        params = QueryParameters(fake_request, fake_view)
        with patch.object(params, "_get_org_unit_account_hierarchy") as mock_method:
            org_unit_access_list = self.test_read_access.get("aws.organizational_unit", {}).get("read", [])
            mock_method.return_value = expected
            result = params._get_org_unit_account_hierarchy(org_unit_access_list)
            mock_method.assert_called_once_with(org_unit_access_list)
            self.assertEqual(result, expected)
