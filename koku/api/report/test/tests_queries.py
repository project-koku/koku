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
"""Test the Report Queries."""
from django.test import TestCase

from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp_aws.query_handler import OCPAWSReportQueryHandler


class ReportQueryUtilsTest(TestCase):
    """Test the report query class functions."""

    HANDLERS = [
        AWSReportQueryHandler,
        AzureReportQueryHandler,
        OCPAzureReportQueryHandler,
        OCPReportQueryHandler,
        OCPAWSReportQueryHandler,
    ]

    def test_has_wildcard_yes(self):
        """Test a list has a wildcard."""
        for handler in self.HANDLERS:
            with self.subTest(handler=handler):
                result = handler.has_wildcard(["abc", "*"])
                self.assertTrue(result)

    def test_has_wildcard_no(self):
        """Test a list doesn't have a wildcard."""
        for handler in self.HANDLERS:
            with self.subTest(handler=handler):
                result = handler.has_wildcard(["abc", "def"])
                self.assertFalse(result)

    def test_has_wildcard_none(self):
        """Test an empty list doesn't have a wildcard."""
        for handler in self.HANDLERS:
            with self.subTest(handler=handler):
                result = handler.has_wildcard([])
                self.assertFalse(result)

    def test_group_data_by_list(self):
        """Test the _group_data_by_list method."""
        for handler in self.HANDLERS:
            with self.subTest(handler=handler):
                # This test checks that the ReportQueryHandler is working. The following data
                # is specific to AWS but should still work for all handlers.
                group_by = ["account", "service"]
                data = [
                    {"account": "a1", "service": "s1", "units": "USD", "total": 4},
                    {"account": "a1", "service": "s2", "units": "USD", "total": 5},
                    {"account": "a2", "service": "s1", "units": "USD", "total": 6},
                    {"account": "a2", "service": "s2", "units": "USD", "total": 5},
                    {"account": "a1", "service": "s3", "units": "USD", "total": 5},
                ]
                out_data = handler._group_data_by_list(group_by, 0, data)
                expected = {
                    "a1": {
                        "s1": [{"account": "a1", "service": "s1", "units": "USD", "total": 4}],
                        "s2": [{"account": "a1", "service": "s2", "units": "USD", "total": 5}],
                        "s3": [{"account": "a1", "service": "s3", "units": "USD", "total": 5}],
                    },
                    "a2": {
                        "s1": [{"account": "a2", "service": "s1", "units": "USD", "total": 6}],
                        "s2": [{"account": "a2", "service": "s2", "units": "USD", "total": 5}],
                    },
                }
                self.assertEqual(expected, out_data)

    def test_group_data_by_list_missing_units(self):
        """Test the _group_data_by_list method when duplicates occur due to missing units."""
        for handler in self.HANDLERS:
            with self.subTest(handler=handler):
                group_by = ["instance_type"]
                data = [
                    {"date": "2018-07-22", "units": "", "instance_type": "t2.micro", "total": 30.0, "count": 0},
                    {"date": "2018-07-22", "units": "Hrs", "instance_type": "t2.small", "total": 17.0, "count": 0},
                    {"date": "2018-07-22", "units": "Hrs", "instance_type": "t2.micro", "total": 1.0, "count": 0},
                ]
                out_data = handler._group_data_by_list(group_by, 0, data)
                expected = {
                    "t2.micro": [
                        {"date": "2018-07-22", "units": "Hrs", "instance_type": "t2.micro", "total": 1.0, "count": 0},
                        {"date": "2018-07-22", "units": "", "instance_type": "t2.micro", "total": 30.0, "count": 0},
                    ],
                    "t2.small": [
                        {"date": "2018-07-22", "units": "Hrs", "instance_type": "t2.small", "total": 17.0, "count": 0}
                    ],
                }
                self.assertEqual(expected, out_data)
