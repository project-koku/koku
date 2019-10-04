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

import random
from unittest.mock import Mock, patch

from django.http import HttpRequest
from django.test import TestCase
from faker import Faker
from querystring_parser import parser
from rest_framework.serializers import ValidationError

from api.models import Tenant
from api.report.serializers import ParamSerializer
from api.report.view import ReportView
from api.query_params import QueryParameters


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

    def test_constructor(self):
        """Test that constructor creates a QueryParameters object."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        self.assertIsInstance(QueryParameters(fake_request, fake_view), QueryParameters)

    def test_constructor_invalid_uri(self):
        """Test that ValidationError is raised with an invalid uri."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.FAKE.paragraph())))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
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
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
                            META=Mock(get=Mock(return_value=expected)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.accept_type, expected)

    def test_access_property(self):
        """Test that the access property returns expected value."""
        expected = self.FAKE.word()
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)),
                            user=Mock(access=expected))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.access, expected)

    def test_delta_property(self):
        """Test that the delta property returns expected value."""
        expected = self.FAKE.word()
        fake_uri = (f'filter[resolution]={self.FAKE.word()}&'
                    f'filter[time_scope_value]={random.randint(0, 9999)}&'
                    f'filter[time_scope_units]={self.FAKE.word()}&'
                    f'delta={expected}')
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.delta, expected)

    def test_tenant_property(self):
        """Test that the tenant property returns expected value."""
        expected = self.FAKE.word()
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(customer=Mock(schema_name=self.FAKE.word())),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
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
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.parameters, expected)

    def test_parameters_property_setter(self):
        """Test that the parameters property setter works."""
        expected = self.FAKE.pydict()
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        params.parameters = expected
        self.assertEqual(params.parameters, expected)

    def test_url_data_property(self):
        """Test that the url_data property returns expected value."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.url_data, self.fake_uri)

    def test_user_property(self):
        """Test that the user property returns expected value."""
        fake_request = Mock(spec=HttpRequest,
                            user=Mock(customer=Mock(schema_name='acct10001')),
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertIsInstance(params.tenant, Tenant)

    def test_get_groupby_default(self):
        """Test that get_group_by() returns the provided default value."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertIsInstance(params.get('group_by'), dict)

    def test_get_set(self):
        """Test that set() assigns the provided value and get() retrieves it."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
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
                            GET=Mock(urlencode=Mock(return_value=self.fake_uri)))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        key = self.FAKE.word()
        value = self.FAKE.word()
        params.set_filter(key=value)
        self.assertEqual(params.get_filter(key), value)

    def test_has_filter_no_filter(self):
        """Test the default filter query parameters."""
        fake_request = Mock(spec=HttpRequest,
                            GET=Mock(urlencode=Mock(return_value='')))
        fake_view = Mock(spec=ReportView,
                         provider=self.FAKE.word(),
                         query_handler=Mock(provider=self.FAKE.word()),
                         report=self.FAKE.word(),
                         serializer=Mock,
                         tag_handler=[])
        params = QueryParameters(fake_request, fake_view)
        self.assertEqual(params.get_filter('time_scope_units'), 'day')
        self.assertEqual(params.get_filter('time_scope_value'), '-10')
        self.assertEqual(params.get_filter('resolution'), 'daily')
