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
import datetime
from unittest.mock import patch
from urllib.parse import quote_plus, urlencode

from dateutil import relativedelta
from django.db.models import F, Sum
from django.http import HttpRequest, QueryDict
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.aws.serializers import QueryParamSerializer
from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.queries import TruncDayString
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.report.view import _generic_report
from api.utils import DateHelper
from reporting.models import OCPUsageLineItemDailySummary


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

    def test_charge_api_has_units(self):
        """Test that the charge API returns units."""
        url = reverse('reports-ocp-charges')
        client = APIClient()
        response = client.get(url, **self.headers)
        response_json = response.json()

        total = response_json.get('total', {})
        data = response_json.get('data', {})
        self.assertTrue('units' in total)
        self.assertEqual(total.get('units'), 'USD')

        for item in data:
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('units' in values)
                self.assertEqual(values.get('units'), 'USD')

    def test_cpu_api_has_units(self):
        """Test that the CPU API returns units."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        response = client.get(url, **self.headers)
        response_json = response.json()

        total = response_json.get('total', {})
        data = response_json.get('data', {})
        self.assertTrue('units' in total)
        self.assertEqual(total.get('units'), 'Core-Hours')

        for item in data:
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('units' in values)
                self.assertEqual(values.get('units'), 'Core-Hours')

    def test_memory_api_has_units(self):
        """Test that the charge API returns units."""
        url = reverse('reports-ocp-memory')
        client = APIClient()
        response = client.get(url, **self.headers)
        response_json = response.json()

        total = response_json.get('total', {})
        data = response_json.get('data', {})
        self.assertTrue('units' in total)
        self.assertEqual(total.get('units'), 'GB-Hours')

        for item in data:
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('units' in values)
                self.assertEqual(values.get('units'), 'GB-Hours')

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

        ten_days_ago = self.dh.n_days_ago(self.dh._now, 10)
        with tenant_context(self.tenant):
            totals = OCPUsageLineItemDailySummary.objects\
                .filter(usage_start__gte=ten_days_ago)\
                .values(*['usage_start'])\
                .annotate(total=Sum('pod_usage_memory_gigabyte_hours'))

        totals = {total.get('usage_start').strftime('%Y-%m-%d'): total.get('total')
                  for total in totals}

        self.assertIn('nodes', data.get('data')[0])

        # Check if limit returns the correct number of results, and
        # that the totals add up properly
        for item in data.get('data'):
            if item.get('nodes'):
                date = item.get('date')
                projects = item.get('nodes')
                self.assertEqual(len(projects), 2)
                self.assertEqual(projects[1].get('node'), '1 Other')
                usage_total = projects[0].get('values')[0].get('usage') + \
                    projects[1].get('values')[0].get('usage')
                self.assertEqual(round(usage_total, 3),
                                 round(float(totals.get(date)), 3))

    def test_execute_query_ocp_charge(self):
        """Test that the charge endpoint is reachable."""
        url = reverse('reports-ocp-charges')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_charge_with_delta(self):
        """Test that deltas work for charge."""
        url = reverse('reports-ocp-charges')
        client = APIClient()
        params = {
            'delta': 'charge',
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        this_month_start = self.dh.this_month_start
        last_month_start = self.dh.last_month_start

        date_delta = relativedelta.relativedelta(months=1)

        def date_to_string(dt):
            return dt.strftime('%Y-%m-%d')

        def string_to_date(dt):
            return datetime.datetime.strptime(dt, '%Y-%m-%d').date()

        with tenant_context(self.tenant):
            current_total = OCPUsageLineItemDailySummary.objects\
                .filter(usage_start__gte=this_month_start)\
                .aggregate(
                    total=Sum(
                        F('pod_charge_cpu_core_hours') +  # noqa: W504
                        F('pod_charge_memory_gigabyte_hours')
                    )
                ).get('total')
            current_total = current_total if current_total is not None else 0

            current_totals = OCPUsageLineItemDailySummary.objects\
                .filter(usage_start__gte=this_month_start)\
                .annotate(**{'date': TruncDayString('usage_start')})\
                .values(*['date'])\
                .annotate(total=Sum(F('pod_charge_cpu_core_hours') + F('pod_charge_memory_gigabyte_hours')))

            prev_totals = OCPUsageLineItemDailySummary.objects\
                .filter(usage_start__gte=last_month_start)\
                .filter(usage_start__lt=this_month_start)\
                .annotate(**{'date': TruncDayString('usage_start')})\
                .values(*['date'])\
                .annotate(total=Sum(F('pod_charge_cpu_core_hours') + F('pod_charge_memory_gigabyte_hours')))

        current_totals = {total.get('date'): total.get('total')
                          for total in current_totals}
        prev_totals = {date_to_string(string_to_date(total.get('date')) + date_delta): total.get('total')
                       for total in prev_totals
                       if date_to_string(string_to_date(total.get('date')) + date_delta) in current_totals}

        prev_total = sum(prev_totals.values())
        prev_total = prev_total if prev_total is not None else 0

        expected_delta = current_total - prev_total
        delta = data.get('delta').get('value')
        self.assertEqual(round(delta, 3), round(float(expected_delta), 3))
        for item in data.get('data'):
            date = item.get('date')
            expected_delta = current_totals.get(date, 0) - prev_totals.get(date, 0)
            values = item.get('values', [])
            delta_value = 0
            if values:
                delta_value = values[0].get('delta_value')
            self.assertEqual(round(delta_value, 3), round(float(expected_delta), 3))

    def test_execute_query_ocp_charge_with_invalid_delta(self):
        """Test that bad deltas don't work for charge."""
        url = reverse('reports-ocp-charges')
        client = APIClient()
        params = {'delta': 'usage'}
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 400)

        params = {'delta': 'request'}
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 400)

    def test_execute_query_ocp_cpu_with_delta_charge(self):
        """Test that charge deltas work for CPU."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'delta': 'charge'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_cpu_with_delta_usage(self):
        """Test that usage deltas work for CPU."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'delta': 'usage'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_cpu_with_delta_request(self):
        """Test that request deltas work for CPU."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'delta': 'request'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_memory_with_delta(self):
        """Test that deltas work for CPU."""
        url = reverse('reports-ocp-memory')
        client = APIClient()
        params = {'delta': 'request'}
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_cpu_with_delta_usage__capacity(self):
        """Test that usage v capacity deltas work."""
        delta = 'usage__capacity'
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'delta': delta
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        delta_one, delta_two = delta.split('__')
        data = response.json()
        for entry in data.get('data', []):
            values = entry.get('values', {})[0]
            delta_percent = (values.get(delta_one)
                             / values.get(delta_two) * 100) \
                            if values.get(delta_two) else 0
            self.assertEqual(round(values.get('delta_percent'), 3), round(delta_percent, 3))

    def test_execute_query_ocp_cpu_with_delta_usage__request(self):
        """Test that usage v request deltas work."""
        delta = 'usage__request'
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'delta': delta
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        delta_one, delta_two = delta.split('__')
        data = response.json()
        for entry in data.get('data', []):
            values = entry.get('values', {})[0]
            delta_percent = (values.get(delta_one)
                             / values.get(delta_two) * 100) \
                            if values.get(delta_two) else 0
            self.assertEqual(round(values.get('delta_percent'), 3), round(delta_percent, 3))

    def test_execute_query_ocp_cpu_with_delta_usage__request(self):
        """Test that request v capacity deltas work."""
        delta = 'request__capacity'
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        params = {
            'delta': delta
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        delta_one, delta_two = delta.split('__')
        data = response.json()
        for entry in data.get('data', []):
            values = entry.get('values', {})[0]
            delta_percent = (values.get(delta_one)
                             / values.get(delta_two) * 100) \
                            if values.get(delta_two) else 0
            self.assertEqual(round(values.get('delta_percent'), 3), round(delta_percent, 3))
