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
"""Test the AWS tag view."""
import calendar
from urllib.parse import quote_plus, urlencode

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.utils import DateHelper


class AWSTagsViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

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

    def test_execute_aws_tags_queries_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        test_cases = [{'value': '-1', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-2', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-10', 'unit': 'day', 'resolution': 'daily'},
                      {'value': '-30', 'unit': 'day', 'resolution': 'daily'}]

        for case in test_cases:
            url = reverse('aws-tags')
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

            self.assertEqual(data.get('data'), [])
            self.assertTrue(isinstance(data.get('data'), list))

    def test_execute_aws_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        test_cases = [{'value': '-1', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-2', 'unit': 'month', 'resolution': 'monthly'},
                      {'value': '-10', 'unit': 'day', 'resolution': 'daily'},
                      {'value': '-30', 'unit': 'day', 'resolution': 'daily'}]

        for case in test_cases:
            url = reverse('aws-tags')
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

            self.assertEqual(data.get('data'), [])
            self.assertTrue(isinstance(data.get('data'), list))
