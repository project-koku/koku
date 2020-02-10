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
from unittest.mock import Mock

from django.db.models import Q
from django.test import TestCase
from faker import Faker

from api.query_params import QueryParameters
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp_aws.query_handler import OCPAWSReportQueryHandler
from api.report.provider_map import ProviderMap
from api.report.queries import ReportQueryHandler

FAKE = Faker()


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


def create_test_handler(mapper=None, params=None):
    """Create a TestableReportQueryHandler using the supplied args."""
    if not mapper:
        mapper = {"filter": {}, "filters": {}}

    if not params:
        params = {"filter": {}, "group_by": {}, "order_by": {}}

    class TestableReportQueryHandler(ReportQueryHandler):
        """ A testable minimal implementation of ReportQueryHandler.

             ReportQueryHandler can't be instantiated directly without first setting
             a few attributes that are required by QueryHandler.__init__().
         """

        _mapper = Mock(
            spec=ProviderMap,
            _report_type_map=Mock(return_value=mapper, get=lambda x, y=None: mapper.get(x, y)),
            _provider_map=Mock(return_value=mapper, get=lambda x, y=None: mapper.get(x, y)),
        )

    mock_params = Mock(
        spec=QueryParameters,
        parameters=Mock(return_value=params, get=lambda x, y=None: params.get(x, y)),
        get_filter=lambda x, default: params.get("filter").get(x, default),
        get_group_by=lambda x, default: params.get("group_by").get(x, default),
        get=lambda x, default: params.get(x, default),
        tag_keys=[],
    )
    return TestableReportQueryHandler(mock_params)


class ReportQueryHandlerTest(TestCase):
    """Test the report query handler functions."""

    def test_init(self):
        """Test that we can instantiate a minimal ReportQueryHandler."""
        rqh = create_test_handler()
        self.assertIsInstance(rqh, ReportQueryHandler)

    def test_set_operator_specified_filters_and(self):
        """Test that AND/OR terms are correctly applied to param filters."""
        operator = "and"

        fake_group = FAKE.word()
        mapper = {"filter": {}, "filters": {}}
        params = {"filter": {}, "group_by": {fake_group: ["and:" + FAKE.word(), "and:" + FAKE.word()]}, "order_by": {}}

        rqh = create_test_handler(mapper, params)
        output = rqh._set_operator_specified_filters(operator)
        self.assertIsNotNone(output)

        expected = Q(**{})
        self.assertEqual(output, expected)

    def test_set_operator_specified_filters_or(self):
        """Test that AND/OR terms are correctly applied to param filters."""
        operator = "or"

        fake_group = FAKE.word()
        mapper = {"filter": {}, "filters": {}, "group_by_options": [fake_group]}
        params = {"filter": {}, "group_by": {fake_group: ["or:" + FAKE.word(), "or:" + FAKE.word()]}, "order_by": {}}

        rqh = create_test_handler(mapper, params)
        output = rqh._set_operator_specified_filters(operator)
        self.assertIsNotNone(output)

        expected = Q(**{})
        self.assertEqual(output, expected)

    def test_set_operator_specified_tag_filters_and(self):
        """Test that AND/OR terms are correctly applied to tag filters."""
        operator = "and"

        fake_group = FAKE.word()
        mapper = {"filter": {}, "filters": {}}
        params = {
            "filter": {},
            "group_by": {fake_group: ["and:tag:" + FAKE.word(), "and:tag:" + FAKE.word()]},
            "order_by": {},
        }

        rqh = create_test_handler(mapper, params)
        output = rqh._set_operator_specified_tag_filters({}, operator)
        self.assertIsNotNone(output)

        self.assertEqual(output, {})

    def test_set_operator_specified_tag_filters_or(self):
        """Test that AND/OR terms are correctly applied to tag filters."""
        operator = "or"

        fake_group = FAKE.word()
        mapper = {"filter": {}, "filters": {}}
        params = {
            "filter": {},
            "group_by": {fake_group: ["or:tag:" + FAKE.word(), "or:tag:" + FAKE.word()]},
            "order_by": {},
        }

        rqh = create_test_handler(mapper, params)
        output = rqh._set_operator_specified_tag_filters({}, operator)
        self.assertIsNotNone(output)

        self.assertEqual(output, {})

    # FIXME: need test for _apply_group_by
    # FIXME: need test for _apply_group_null_label
    # FIXME: need test for _build_custom_filter_list  }
    # FIXME: need test for _create_previous_totals
    # FIXME: need test for _get_filter
    # FIXME: need test for _get_group_by
    # FIXME: need test for _get_previous_totals_filter
    # FIXME: need test for _get_search_filter
    # FIXME: need test for _get_tag_group_by
    # FIXME: need test for _group_data_by_list
    # FIXME: need test for _pack_data_object
    # FIXME: need test for _percent_delta
    # FIXME: need test for _perform_rank_summation
    # FIXME: need test for _ranked_list
    # FIXME: need test for _set_or_filters
    # FIXME: need test for _set_tag_filters
    # FIXME: need test for _transform_data
    # FIXME: need test for add_deltas
    # FIXME: need test for annotations
    # FIXME: need test for date_group_data
    # FIXME: need test for get_tag_filter_keys
    # FIXME: need test for get_tag_group_by_keys
    # FIXME: need test for get_tag_order_by
    # FIXME: need test for initialize_totals
    # FIXME: need test for order_by
    # FIXME: need test for unpack_date_grouped_data
