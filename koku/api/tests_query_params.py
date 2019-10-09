#
# Copyright 2019 Red Hat, Inc.
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
"""Test the QueryParameters."""

import logging
import random
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.test import TestCase
from faker import Faker
from querystring_parser import parser
from rest_framework.serializers import ValidationError

from api.models import Tenant, User
from api.query_params import QueryParameters, get_tenant
from api.report.serializers import ParamSerializer
from api.report.view import ReportView

LOG = logging.getLogger(__name__)
PROVIDERS = ['AWS', 'AZURE', 'OCP', 'OCP_AWS']
ACCESS_KEYS = {'aws': ['aws.account'],
               'azure': ['azure.subscription_guid'],
               'ocp': ['openshift.cluster',
                       'openshift.project',
                       'openshift.node'],
               'ocp_aws': ['aws.account',
                           'openshift.cluster',
                           'openshift.project',
                           'openshift.node']}


class QueryParametersTests(TestCase):
    """Unit tests for QueryParameters."""

    FAKE = Faker()

    def setUp(self):
        """Test setup."""
        self.fake_uri = (f'filter[resolution]={self.FAKE.word()}&'
                         f'filter[time_scope_value]={random.randint(0, 9999)}&'
                         f'filter[time_scope_units]={self.FAKE.word()}&'
                         f'group_by[{self.FAKE.word()}]=*&'
                         f'order_by[{self.FAKE.word()}]=asc')
        self.provider = random.choice(PROVIDERS).lower()
        self.test_read_access = {random.choice(ACCESS_KEYS[self.provider]): {'read': ['*']}}

    def test_constructor(self):
        """Test that constructor creates a QueryParameters object.

        This test is a bit fatter than it needs to be to help show how to mock
        out the Request and View objects.
        """
        def fake_tags():
            fake_tags = []
            for _ in range(0, random.randint(2, 10)):
                fake_tags.append({'key': self.FAKE.word(),
                                  'value': self.FAKE.word()})
            return fake_tags

        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=Mock(get=lambda key, default: default),
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=random.choice(PROVIDERS)),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[Mock(objects=Mock(values=lambda _: fake_tags())),
                                      Mock(objects=Mock(values=lambda _: fake_tags()))])
        self.assertIsInstance(QueryParameters(fake_request, fake_view), QueryParameters)

    def test_constructor_invalid_uri(self):
        """Test that ValidationError is raised with an invalid uri."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.FAKE.paragraph())))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report='tags',
                         serializer=Mock,
                         tag_handler=[])
        with self.assertRaises(ValidationError):
            QueryParameters(fake_request, fake_view)

    def test_constructor_invalid_data(self):
        """Test that ValidationError is raised when serializer data is invalid."""
        class MockSerializer(Mock):
            """Mock Serializer for testing validity."""

            def __init__(self, *args, **kwargs):
                """Constructor."""
                super().__init__(*args,
                                 spec=ParamSerializer,
                                 is_valid=lambda: False,
                                 **kwargs)

        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=MockSerializer,
                         tag_handler=[])
        with self.assertRaises(ValidationError):
            QueryParameters(fake_request, fake_view)

    def test_accept_type_property(self):
        """Test that the accept_type property returns expected value."""
        expected = self.FAKE.word()
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
                            META=Mock(get=Mock(return_value=expected)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.accept_type, expected)

    def test_access_property(self):
        """Test that the access property returns expected value."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
                            user=Mock(access=self.test_read_access, customer=Mock(schema_name=self.FAKE.word())))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.access, self.test_read_access)

    def test_delta_property(self):
        """Test that the delta property returns expected value."""
        expected = self.FAKE.word()
        fake_uri = f'delta={expected}'
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.delta, expected)

    def test_tenant_property(self):
        """Test that the tenant property returns expected value."""
        expected = self.FAKE.word()
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        with patch('api.query_params.get_tenant', return_value=expected):
            params = QueryParameters(fake_request, fake_view)
            self.assertEqual(params.tenant, expected)

    def test_parameters_property(self):
        """Test that the parameters property returns expected value."""
        expected = parser.parse(str(self.fake_uri))
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.parameters, expected)

    def test_parameters_property_setter(self):
        """Test that the parameters property setter works."""
        expected = self.FAKE.pydict()
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        params.parameters = expected
        self.assertEqual(params.parameters, expected)

    def test_url_data_property(self):
        """Test that the url_data property returns expected value."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.url_data, self.fake_uri)

    def test_user_property(self):
        """Test that the user property returns expected value."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertIsInstance(params.tenant, Tenant)

    def test_get_groupby_default(self):
        """Test that get_group_by() returns the provided default value."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertIsInstance(params.get('group_by'), dict)

    def test_get_set(self):
        """Test that set() assigns the provided value and get() retrieves it."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        key = self.FAKE.word()
        value = self.FAKE.word()
        params.set(key, value)
        self.assertEqual(params.get(key), value)

    def test_get_set_filter(self):
        """Test that set() assigns the provided value and get() retrieves it."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        key = self.FAKE.word()
        value = self.FAKE.word()
        params.set_filter(**{key: value})
        self.assertEqual(params.get_filter(key), value)

    def test_has_filter_no_filter(self):
        """Test the default filter query parameters."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value='')))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('time_scope_units'), 'day')
        self.assertEqual(params.get_filter('time_scope_value'), '-10')
        self.assertEqual(params.get_filter('resolution'), 'daily')

    def test_has_filter_no_value(self):
        """Test the default filter parameters when time_scope_value is undefined."""
        fake_uri = ('filter[resolution]=monthly&'
                    'filter[time_scope_units]=month')
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('time_scope_value'), '-1')

    def test_has_filter_no_units(self):
        """Test the default filter parameters when time_scope_units is undefined."""
        fake_uri = ('filter[resolution]=monthly&'
                    'filter[time_scope_value]=-1')
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('time_scope_units'), 'month')

    def test_has_filter_no_resolution(self):
        """Test the default filter parameters when resolution is undefined."""
        fake_uri = ('filter[time_scope_units]=month&'
                    'filter[time_scope_value]=-1')
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=None, customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('resolution'), 'monthly')

    def test_access_with_wildcard(self):
        """Test wildcard doesn't update query parameters."""
        provider = random.choice(PROVIDERS)
        fake_uri = ('group_by[account]=*&'
                    'group_by[region]=*')
        test_access = {
            f'{provider}.account': {'read': ['*']}
        }
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=provider),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_group_by('account'), '*')
        self.assertEqual(params.get_group_by('region'), '*')

    def test_access_replace_wildcard(self):
        """Test that a group by account wildcard is replaced with only the subset of accounts."""
        fake_uri = ('group_by[account]=*&'
                    'group_by[region]=*')
        test_access = {'aws.account': {'read': ['account1', 'account2']}}
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider='AWS'),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_group_by('account'), ['account1', 'account2'])
        self.assertEqual(params.get_group_by('region'), '*')

    def test_access_gb_filtered_intersection(self):
        """Test that a group by account filtered list is replaced with only the intersection of accounts."""
        guid1 = uuid4()
        guid2 = uuid4()
        guid3 = uuid4()
        fake_uri = (f'group_by[subscription_guid]={guid1}&'
                    f'group_by[subscription_guid]={guid2}&'
                    f'group_by[resource_location]=*')
        test_access = {'azure.subscription_guid': {'read': [str(guid1), str(guid3)]}}
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider='AZURE'),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_group_by('subscription_guid'), [str(guid1)])
        self.assertEqual(params.get_group_by('resource_location'), '*')

    def test_access_empty_intersection(self):
        """Test that a group by cluster filtered list causes 403 with empty intersection."""
        fake_uri = ('group_by[cluster]=cluster1&'
                    'group_by[cluster]=cluster3')
        test_access = {'openshift.cluster': {'read': ['cluster4', 'cluster2']}}
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider='OCP'),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        with self.assertRaises(PermissionDenied):
            QueryParameters(fake_request, fake_view)

    def test_access_add_account_filter(self):
        """Test that if no group_by or filter is present a filter of accounts is added."""
        fake_uri = 'filter[region]=*'
        test_access = {'aws.account': {'read': ['account1', 'account2']}}
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider='AWS'),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('account'), ['account1', 'account2'])
        self.assertEqual(params.get_filter('region'), '*')

    def test_update_query_parameters_add_subscription_guid_filter_obj(self):
        """Test that if no group_by or filter is present a filter of subscription_guids is added."""
        guid1 = uuid4()
        guid2 = uuid4()
        test_access = {'azure.subscription_guid': {'read': [guid1, guid2]}}
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value='')))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider='AZURE'),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('subscription_guid'), [guid1, guid2])

    def test_update_query_parameters_filtered_intersection(self):
        """Test that a filter by cluster filtered list is replaced with only the intersection of cluster."""
        fake_uri = ('filter[cluster]=cluster1&'
                    'filter[cluster]=cluster3')
        test_access = {'openshift.cluster': {'read': ['cluster1', 'cluster2']}}
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=test_access,
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider='OCP'),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('cluster'), ['cluster1'])

    def test_get_tenant(self):
        """Test that get_tenant() returns a Tenant."""
        user = Mock(customer=Mock(schema_name='acct10001'))
        self.assertIsInstance(get_tenant(user), Tenant)

    def test_get_tenant_invalid(self):
        """Test that get_tenant() raises ValidationError when user is invalid."""
        with self.assertRaises(ValidationError):
            get_tenant(None)

    def test_get_tenant_no_user(self):
        """Test that get_tenant() raises ValidationError when user is missing."""
        user = Mock(customer=Mock(schema_name='acct10001'))
        with patch('api.query_params.Tenant.objects.get', side_effect=User.DoesNotExist):
            with self.assertRaises(ValidationError):
                get_tenant(user)

    def test_process_tag_query_params(self):
        """Test that a list of tag keys is reduced to those queried."""
        fake_uri = ('filter[resolution]=monthly&'
                    'filter[time_scope_value]=-1&'
                    'filter[time_scope_units]=month&'
                    'filter[tag:environment]=prod&'
                    'group_by[tag:app]=*')
        tag_keys = ['app', 'az', 'environment', 'cost_center',
                    'fake', 'other', 'this']
        expected = set(['tag:app', 'tag:environment'])

        fake_request = Mock(spec=HttpRequest,
                            user=Mock(access=Mock(get=lambda key, default: default),
                                      customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_objects = Mock(values=lambda _: [{'key': key,
                                               'value': self.FAKE.word()} for key in tag_keys])
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=random.choice(PROVIDERS)),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[Mock(objects=fake_objects)])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.tag_keys, expected)
