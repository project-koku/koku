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
"""Test the OCP tag view."""
import calendar
import datetime
from urllib.parse import quote_plus, urlencode

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.test import create_generic_provider
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.utils import DateHelper
from reporting.models import OCPUsageLineItemDailySummary


class OCPTagsViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.ten_days_ago = cls.dh.n_days_ago(cls.dh._now, 9)

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        _, self.provider = create_generic_provider('OCP', self.headers)
        self.data_generator = OCPReportDataGenerator(self.tenant, self.provider)
        self.data_generator.add_data_to_tenant()

    def _calculate_expected_range(self, time_scope_value, time_scope_units):
        today = self.dh.today

        if time_scope_value == '-1' and time_scope_units == 'month':
            start_range = today.replace(day=1).date()
        elif time_scope_value == '-2' and time_scope_units == 'month':
            start_range = (today - relativedelta(months=1)).replace(day=1).date()
        elif time_scope_value == '-10' and time_scope_units == 'day':
            start_range = (today - relativedelta(days=10)).date()
        elif time_scope_value == '-30' and time_scope_units == 'day':
            start_range = (today - relativedelta(days=30)).date()

        end_range = today.replace(day=calendar.monthrange(today.year, today.month)[1]).date()

        return start_range, end_range

    def test_execute_ocp_tags_queries_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        test_cases = [{'value': '-1', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-2', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-10', 'unit': 'day', 'resolution': 'daily'},
                      {'value': '-30', 'unit': 'day', 'resolution': 'daily'}]

        for case in test_cases:
            url = reverse('openshift-tags')
            client = APIClient()
            params = {
                'filter[resolution]': case.get('resolution'),
                'filter[time_scope_value]': case.get('value'),
                'filter[time_scope_units]': case.get('unit'),
                'key_only': True
            }
            url = url + '?' + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            start_range, end_range = self._calculate_expected_range(case.get('value'), case.get('unit'))

            for label in data.get('data'):
                label_date = datetime.datetime.strptime(label.split('*')[0], '%m-%d-%Y')
                self.assertGreaterEqual(label_date.date(), start_range)
                self.assertLessEqual(label_date.date(), end_range)

            self.assertTrue(data.get('data'))
            self.assertTrue(isinstance(data.get('data'), list))

    def test_execute_ocp_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        test_cases = [{'value': '-1', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-2', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-10', 'unit': 'day', 'resolution': 'daily'},
                      {'value': '-30', 'unit': 'day', 'resolution': 'daily'}]

        for case in test_cases:
            url = reverse('openshift-tags')
            client = APIClient()
            params = {
                'filter[resolution]': case.get('resolution'),
                'filter[time_scope_value]': case.get('value'),
                'filter[time_scope_units]': case.get('unit'),
                'key_only': False
            }
            url = url + '?' + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            start_range, end_range = self._calculate_expected_range(case.get('value'), case.get('unit'))

            for tag in data.get('data'):
                label = tag.get('key')
                label_date = datetime.datetime.strptime(label.split('*')[0], '%m-%d-%Y')
                self.assertGreaterEqual(label_date.date(), start_range)
                self.assertLessEqual(label_date.date(), end_range)
                self.assertIsNotNone(tag.get('values'))

            self.assertTrue(data.get('data'))
            self.assertTrue(isinstance(data.get('data'), list))

    def test_execute_ocp_tags_type_queries(self):
        """Test that tag data is for the correct type queries."""
        test_cases = [{'value': '-1', 'unit': 'month', 'resolution': 'monthly', 'type': 'pod'},
                      {'value': '-2', 'unit': 'month', 'resolution': 'monthly', 'type': 'pod'},
                      {'value': '-10', 'unit': 'day', 'resolution': 'daily', 'type': 'pod'},
                      {'value': '-30', 'unit': 'day', 'resolution': 'daily', 'type': 'storage'}]

        for case in test_cases:
            url = reverse('openshift-tags')
            client = APIClient()
            params = {
                'filter[resolution]': case.get('resolution'),
                'filter[time_scope_value]': case.get('value'),
                'filter[time_scope_units]': case.get('unit'),
                'key_only': False,
                'filter[type]': case.get('type')
            }
            url = url + '?' + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            start_range, end_range = self._calculate_expected_range(case.get('value'), case.get('unit'))

            for tag in data.get('data'):
                label = tag.get('key')
                label_date = datetime.datetime.strptime(label.split('*')[0], '%m-%d-%Y')
                self.assertGreaterEqual(label_date.date(), start_range)
                self.assertLessEqual(label_date.date(), end_range)
                self.assertIsNotNone(tag.get('values'))

            self.assertTrue(data.get('data'))
            self.assertTrue(isinstance(data.get('data'), list))

    def test_execute_query_with_and_filter(self):
        """Test the filter[and:] param in the view."""
        url = reverse('openshift-tags')
        client = APIClient()

        with tenant_context(self.tenant):
            projects = OCPUsageLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .values('namespace').distinct()
            projects = [project.get('namespace') for project in projects]
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-10',
            'filter[time_scope_units]': 'day',
            'filter[and:project]': projects
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(response_data.get('data', []), [])
