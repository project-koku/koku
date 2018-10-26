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

from django.http import HttpRequest, QueryDict
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.aws.aws_query_handler import AWSReportQueryHandler
from api.report.aws.serializers import QueryParamSerializer
from api.report.ocp.ocp_query_handler_cpu import OCPReportQueryHandlerCPU
from api.report.ocp.ocp_query_handler_mem import OCPReportQueryHandlerMem
from api.report.view import (_convert_units,
                             _fill_in_missing_units,
                             _find_unit,
                             _generic_report,
                             process_query_parameters)
from api.utils import UnitConverter


class OCPReportViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.report_ocp_cpu = {
            "group_by": {
                "project": [
                    "*"
                ]
            },
            "filter": {
                "resolution": "monthly",
                "time_scope_value": "-1",
                "time_scope_units": "month"
            },
            "data": [
                {
                    "date": "2018-10",
                    "projects": [
                        {
                            "project": "default",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "default",
                                    "cpu_limit": 'null',
                                    "cpu_usage_core_hours": 0.119385,
                                    "cpu_requests_core_hours": 9.506666
                                }
                            ]
                        },
                        {
                            "project": "metering",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "metering",
                                    "cpu_limit": 'null',
                                    "cpu_usage_core_hours": 4.464511,
                                    "cpu_requests_core_hours": 53.985832
                                }
                            ]
                        },
                        {
                            "project": "monitoring",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "monitoring",
                                    "cpu_limit": 'null',
                                    "cpu_usage_core_hours": 7.861343,
                                    "cpu_requests_core_hours": 17.920067
                                }
                            ]
                        },
                        {
                            "project": "openshift-web-console",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "openshift-web-console",
                                    "cpu_limit": 'null',
                                    "cpu_usage_core_hours": 0.862687,
                                    "cpu_requests_core_hours": 4.753333
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "pod_usage_cpu_core_hours": 13.307928,
                "pod_request_cpu_core_hours": 86.165898
            }
        }
        self.report_ocp_mem = {
            "group_by": {
                "project": [
                    "*"
                ]
            },
            "filter": {
                "resolution": "monthly",
                "time_scope_value": "-1",
                "time_scope_units": "month"
            },
            "data": [
                {
                    "date": "2018-10",
                    "projects": [
                        {
                            "project": "default",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "default",
                                    "memory_usage_gigabytes": 0.162249,
                                    "memory_requests_gigabytes": 1.063302
                                }
                            ]
                        },
                        {
                            "project": "metering",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "metering",
                                    "memory_usage_gigabytes": 5.899788,
                                    "memory_requests_gigabytes": 7.007081
                                }
                            ]
                        },
                        {
                            "project": "monitoring",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "monitoring",
                                    "memory_usage_gigabytes": 3.178287,
                                    "memory_requests_gigabytes": 4.153526
                                }
                            ]
                        },
                        {
                            "project": "openshift-web-console",
                            "values": [
                                {
                                    "date": "2018-10",
                                    "project": "openshift-web-console",
                                    "memory_usage_gigabytes": 0.068988,
                                    "memory_requests_gigabytes": 0.207677
                                }
                            ]
                        }
                    ]
                }
            ],
            "total": {
                "pod_usage_memory_gigabytes": 9.309312,
                "pod_request_memory_gigabytes": 12.431585
            }
        }

    @patch('api.report.ocp.ocp_query_handler_cpu.OCPReportQueryHandlerCPU')
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
        response = _generic_report(request, QueryParamSerializer, OCPReportQueryHandlerCPU, **extras)
        self.assertIsInstance(response, Response)

    @patch('api.report.ocp.ocp_query_handler_mem.OCPReportQueryHandlerMem')
    def test_generic_report_ocp_cpu_success(self, mock_handler):
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
        response = _generic_report(request, QueryParamSerializer, OCPReportQueryHandlerMem, **extras)
        self.assertIsInstance(response, Response)

    def test_execute_query_ocp_cpu(self):
        """Test that OCP CPU endpoint works."""
        url = reverse('reports-ocp-cpu')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_ocp_memory(self):
        """Test that OCP Mem endpoint works"""
        url = reverse('reports-ocp-memory')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
