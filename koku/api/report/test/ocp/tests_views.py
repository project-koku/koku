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
"""Test the Report views."""
from unittest.mock import patch
from urllib.parse import quote_plus, urlencode

from django.http import HttpRequest, QueryDict
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.aws.serializers import QueryParamSerializer
from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.report.view import _generic_report
from api.utils import DateHelper


class OCPReportViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.data_generator = OCPReportDataGenerator(self.tenant)
        self.data_generator.add_data_to_tenant()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.report_ocp_cpu = {
            'group_by': {
                'project': [
                    '*'
                ]
            },
            'filter': {
                'resolution': 'monthly',
                'time_scope_value': '-1',
                'time_scope_units': 'month'
            },
            'data': [
                {
                    'date': '2018-10',
                    'projects': [
                        {
                            'project': 'default',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'default',
                                    'limit': 'null',
                                    'usage': 0.119385,
                                    'request': 9.506666
                                }
                            ]
                        },
                        {
                            'project': 'metering',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'metering',
                                    'limit': 'null',
                                    'usage': 4.464511,
                                    'request': 53.985832
                                }
                            ]
                        },
                        {
                            'project': 'monitoring',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'monitoring',
                                    'limit': 'null',
                                    'usage': 7.861343,
                                    'request': 17.920067
                                }
                            ]
                        },
                        {
                            'project': 'openshift-web-console',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'openshift-web-console',
                                    'limit': 'null',
                                    'usage': 0.862687,
                                    'request': 4.753333
                                }
                            ]
                        }
                    ]
                }
            ],
            'total': {
                'pod_usage_cpu_core_hours': 13.307928,
                'pod_request_cpu_core_hours': 86.165898
            }
        }
        self.report_ocp_mem = {
            'group_by': {
                'project': [
                    '*'
                ]
            },
            'filter': {
                'resolution': 'monthly',
                'time_scope_value': '-1',
                'time_scope_units': 'month'
            },
            'data': [
                {
                    'date': '2018-10',
                    'projects': [
                        {
                            'project': 'default',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'default',
                                    'memory_usage_gigabytes': 0.162249,
                                    'memory_requests_gigabytes': 1.063302
                                }
                            ]
                        },
                        {
                            'project': 'metering',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'metering',
                                    'memory_usage_gigabytes': 5.899788,
                                    'memory_requests_gigabytes': 7.007081
                                }
                            ]
                        },
                        {
                            'project': 'monitoring',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'monitoring',
                                    'memory_usage_gigabytes': 3.178287,
                                    'memory_requests_gigabytes': 4.153526
                                }
                            ]
                        },
                        {
                            'project': 'openshift-web-console',
                            'values': [
                                {
                                    'date': '2018-10',
                                    'project': 'openshift-web-console',
                                    'memory_usage_gigabytes': 0.068988,
                                    'memory_requests_gigabytes': 0.207677
                                }
                            ]
                        }
                    ]
                }
            ],
            'total': {
                'pod_usage_memory_gigabytes': 9.309312,
                'pod_request_memory_gigabytes': 12.431585
            }
        }

    @patch('api.report.ocp.ocp_query_handler.OCPReportQueryHandler')
    def test_generic_report_ocp_cpu_success(self, mock_handler):
        """Test OCP cpu generic report."""
        mock_handler.return_value.execute_query.return_value = self.report_ocp_cpu
        params = {
            'group_by[account]': '*',
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        user = User.objects.get(
            username=self.user_data['username']
        )

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        extras = {'report_type': 'cpu'}
        response = _generic_report(request, QueryParamSerializer, OCPReportQueryHandler, **extras)
        self.assertIsInstance(response, Response)

    @patch('api.report.ocp.ocp_query_handler.OCPReportQueryHandler')
    def test_generic_report_ocp_mem_success(self, mock_handler):
        """Test OCP memory generic report."""
        mock_handler.return_value.execute_query.return_value = self.report_ocp_mem
        params = {
            'group_by[account]': '*',
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        user = User.objects.get(
            username=self.user_data['username']
        )

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        extras = {'report_type': 'mem'}
        response = _generic_report(request, QueryParamSerializer, OCPReportQueryHandler, **extras)
        self.assertIsInstance(response, Response)

    def test_execute_query_ocp_cpu(self):
        """Test that OCP CPU endpoint works."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        response = client.get(url, **self.headers)

        expected_end_date = self.dh.today
        expected_start_date = self.dh.n_days_ago(expected_end_date, 9)
        expected_end_date = str(expected_end_date.date())
        expected_start_date = str(expected_start_date.date())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('limit' in values)
                self.assertTrue('usage' in values)
                self.assertTrue('request' in values)

    def test_execute_query_ocp_cpu_last_thirty_days(self):
        """Test that OCP CPU endpoint works."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {'filter[time_scope_value]': '-30'}
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_end_date = self.dh.today
        expected_start_date = self.dh.n_days_ago(expected_end_date, 29)
        expected_end_date = str(expected_end_date.date())
        expected_start_date = str(expected_start_date.date())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('limit' in values)
                self.assertTrue('usage' in values)
                self.assertTrue('request' in values)

    def test_execute_query_ocp_cpu_this_month(self):
        """Test that data is returned for the full month."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_date = self.dh.today.strftime('%Y-%m')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_date)

        values = data.get('data')[0].get('values')[0]
        self.assertTrue('limit' in values)
        self.assertTrue('usage' in values)
        self.assertTrue('request' in values)

    def test_execute_query_ocp_cpu_this_month_daily(self):
        """Test that data is returned for the full month."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_start_date = self.dh.this_month_start.strftime('%Y-%m-%d')
        expected_end_date = self.dh.this_month_end.strftime('%Y-%m-%d')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('limit' in values)
                self.assertTrue('usage' in values)
                self.assertTrue('request' in values)

    def test_execute_query_ocp_cpu_last_month(self):
        """Test that data is returned for the last month."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_date = self.dh.last_month_start.strftime('%Y-%m')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_date)

        values = data.get('data')[0].get('values')[0]
        self.assertTrue('limit' in values)
        self.assertTrue('usage' in values)
        self.assertTrue('request' in values)

    def test_execute_query_ocp_cpu_last_month_daily(self):
        """Test that data is returned for the full month."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_start_date = self.dh.last_month_start.strftime('%Y-%m-%d')
        expected_end_date = self.dh.last_month_end.strftime('%Y-%m-%d')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('limit' in values)
                self.assertTrue('usage' in values)
                self.assertTrue('request' in values)

    def test_execute_query_ocp_memory(self):
        """Test that OCP Mem endpoint works."""
        url = reverse('reports-ocp-memory')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_memory_group_by_limit(self):
        """Test that OCP Mem endpoint works with limits."""
        url = reverse('reports-ocp-memory')
        client = APIClient()
        params = {
            'group_by[node]': '*',
            'filter[limit]': '1',
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        data = response.json()

        self.assertIn('nodes', data.get('data')[0])

        for item in data.get('data'):
            if item.get('nodes'):
                projects = item.get('nodes')
                print(projects)
                self.assertEqual(len(projects), 2)
                self.assertEqual(projects[1].get('node'), 'Other')
