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
"""Test the Azure Provider views."""

from unittest.mock import patch

from django.http import HttpRequest, QueryDict
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.common.pagination import ReportPagination, ReportRankedPagination
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.azure.view import AzureCostView
from api.report.view import (_convert_units,
                             _fill_in_missing_units,
                             _find_unit,
                             get_paginator)
from api.utils import UnitConverter

FAKE = Faker()


class AzureReportViewTest(IamTestCase):
    """Azure report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.report = {
            'group_by': {
                'subscription_guid': ['*']
            },
            'filter': {
                'resolution': 'monthly',
                'time_scope_value': -1,
                'time_scope_units': 'month',
                'resource_scope': []
            },
            'data': [
                {
                    'date': '2018-07',
                    'subscription_guids': [
                        {
                            'subscription_guid': '00000000-0000-0000-0000-000000000000',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'subscription_guid': '00000000-0000-0000-0000-000000000000',
                                    'total': 1826.74238146924
                                }
                            ]
                        },
                        {
                            'subscription_guid': '11111111-1111-1111-1111-111111111111',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'subscription_guid': '11111111-1111-1111-1111-111111111111',
                                    'total': 1137.74036198065
                                }
                            ]
                        },
                        {
                            'subscription_guid': '22222222-2222-2222-2222-222222222222',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'subscription_guid': '22222222-2222-2222-2222-222222222222',
                                    'total': 1045.80659412797
                                }
                            ]
                        },
                        {
                            'subscription_guid': '33333333-3333-3333-3333-333333333333',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'subscription_guid': '33333333-3333-3333-3333-333333333333',
                                    'total': 807.326470618818
                                }
                            ]
                        },
                        {
                            'subscription_guid': '44444444-4444-4444-4444-444444444444',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'subscription_guid': '44444444-4444-4444-4444-444444444444',
                                    'total': 658.306642830709
                                }
                            ]
                        }
                    ]
                }
            ],
            'total': {
                'value': 5475.922451027388,
                'units': 'GB-Mo'
            }
        }

    def test_get_costs_customer_owner(self):
        """Test costs reports runs with a customer owner."""
        url = reverse('reports-azure-costs')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_instance_customer_owner(self):
        """Test inventory instance reports runs with a customer owner."""
        url = reverse('reports-azure-instance-type')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_storage_customer_owner(self):
        """Test inventory storage reports runs with a customer owner."""
        url = reverse('reports-azure-storage')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_costs_invalid_query_param(self):
        """Test costs reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=subscription_guid1&filter%5Bresolution%5D=daily'
        url = reverse('reports-azure-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_instance_usage_invalid_query_param(self):
        """Test instance usage reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=subscription_guid1&filter%5Bresolution%5D=daily'
        url = reverse('reports-azure-instance-type') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_storage_usage_invalid_query_param(self):
        """Test storage usage reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=subscription_guid1&filter%5Bresolution%5D=daily'
        url = reverse('reports-azure-storage') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_costs_csv(self):
        """Test CSV output of costs reports."""
        url = reverse('reports-azure-costs')
        client = APIClient(HTTP_ACCEPT='text/csv')

        response = client.get(url, **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_instance_csv(self):
        """Test CSV output of inventory instance reports."""
        url = reverse('reports-azure-instance-type')
        client = APIClient(HTTP_ACCEPT='text/csv')
        response = client.get(url, content_type='text/csv', **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_storage_csv(self):
        """Test CSV output of inventory storage reports."""
        url = reverse('reports-azure-storage')
        client = APIClient(HTTP_ACCEPT='text/csv')
        response = client.get(url, content_type='text/csv', **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_convert_units_success(self):
        """Test unit conversion succeeds."""
        converter = UnitConverter()
        to_unit = 'byte'
        expected_unit = f'{to_unit}-Mo'
        report_total = self.report.get('total', {}).get('value')

        result = _convert_units(converter, self.report, to_unit)
        result_unit = result.get('total', {}).get('units')
        result_total = result.get('total', {}).get('value')

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1E9, result_total)

    def test_convert_units_list(self):
        """Test that the list check is hit."""
        converter = UnitConverter()
        to_unit = 'byte'
        expected_unit = f'{to_unit}-Mo'
        report_total = self.report.get('total', {}).get('value')

        report = [self.report]
        result = _convert_units(converter, report, to_unit)
        result_unit = result[0].get('total', {}).get('units')
        result_total = result[0].get('total', {}).get('value')

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1E9, result_total)

    def test_convert_units_total_not_dict(self):
        """Test that the total not dict block is hit."""
        converter = UnitConverter()
        to_unit = 'byte'
        expected_unit = f'{to_unit}-Mo'

        report = self.report['data'][0]['subscription_guids'][0]['values'][0]
        report_total = report.get('total')
        result = _convert_units(converter, report, to_unit)
        result_unit = result.get('units')
        result_total = result.get('total')

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1E9, result_total)

    @patch('api.report.azure.query_handler.AzureReportQueryHandler')
    def test_costview_with_units_success(self, mock_handler):
        """Test unit conversion succeeds in AzureCostView."""
        mock_handler.return_value.execute_query.return_value = self.report
        params = {
            'group_by[subscription_guid]': '*',
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'units': 'byte',
            'SERVER_NAME': ''
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

        response = AzureCostView().get(request)
        self.assertIsInstance(response, Response)

    def test_find_unit_list(self):
        """Test that the correct unit is returned."""
        expected_unit = 'Hrs'
        data = [
            {'date': '2018-07-22', 'units': '',
             'instance_type': 'Standard_A1_v2', 'total': 30.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit,
             'instance_type': 'Standard_A2m_v2', 'total': 17.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit,
             'instance_type': 'Standard_A1_v2', 'total': 1.0, 'count': 0}
        ]

        result_unit = _find_unit()(data)
        self.assertEqual(expected_unit, result_unit)

    def test_find_unit_dict(self):
        """Test that the correct unit is returned for a dictionary."""
        data = {'date': '2018-07-22', 'units': '',
                'instance_type': 'Standard_A1_v2', 'total': 30.0, 'count': 0},

        result_unit = _find_unit()(data)
        self.assertIsNone(result_unit)

    def test_fill_in_missing_units_list(self):
        """Test that missing units are filled in."""
        expected_unit = 'Hrs'
        data = [
            {'date': '2018-07-22', 'units': '',
             'instance_type': 'Standard_A1_v2', 'total': 30.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit,
             'instance_type': 'Standard_A2m_v2', 'total': 17.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit,
             'instance_type': 'Standard_A1_v2', 'total': 1.0, 'count': 0}
        ]

        unit = _find_unit()(data)

        result = _fill_in_missing_units(unit)(data)

        for entry in result:
            self.assertEqual(entry.get('units'), expected_unit)

    def test_fill_in_missing_units_dict(self):
        """Test that missing units are filled in for a dictionary."""
        expected_unit = 'Hrs'
        data = {'date': '2018-07-22', 'units': '', 'instance_type': 'Standard_A1_v2', 'total': 30.0, 'count': 0}

        result = _fill_in_missing_units(expected_unit)(data)

        self.assertEqual(result.get('units'), expected_unit)

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        qs = 'delta=cost'
        url = reverse('reports-azure-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = 'Invalid'
        expected = f'"{bad_delta}" is not a valid choice.'
        qs = f'group_by[subscription_guid]=*&filter[limit]=2&delta={bad_delta}'
        url = reverse('reports-azure-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        result = str(response.data.get('delta')[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)

    def test_get_paginator_default(self):
        """Test that the standard report paginator is returned."""
        params = {}
        paginator = get_paginator(params, 0)

        self.assertIsInstance(paginator, ReportPagination)

    def test_get_paginator_for_filter_offset(self):
        """Test that the standard report paginator is returned."""
        params = {'offset': 5}
        paginator = get_paginator(params, 0)

        self.assertIsInstance(paginator, ReportRankedPagination)
