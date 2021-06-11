#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
from unittest.mock import Mock

from django.test import TestCase
from faker import Faker

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.aws.openshift.query_handler import OCPAWSReportQueryHandler
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.provider_map import ProviderMap
from api.report.queries import ReportQueryHandler
from api.report.view import ReportView
from api.utils import DateHelper

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


def create_test_handler(params, mapper=None):
    """Create a TestableReportQueryHandler using the supplied args.

    Args:

    params (QueryParameters) mocked query parameters
    mapper (dict) mocked ProviderMap dictionary
    """
    if not mapper:
        mapper = {"filter": [{}], "filters": {}}

    class TestableReportQueryHandler(ReportQueryHandler):
        """A testable minimal implementation of ReportQueryHandler.

        ReportQueryHandler can't be instantiated directly without first setting
        a few attributes that are required by QueryHandler.__init__().
        """

        _mapper = Mock(
            spec=ProviderMap,
            _report_type_map=Mock(return_value=mapper, get=lambda x, y=None: mapper.get(x, y)),
            _provider_map=Mock(return_value=mapper, get=lambda x, y=None: mapper.get(x, y)),
            tag_column="tags",
        )

    return TestableReportQueryHandler(params)


def assertSameQ(one, two):
    """Compare two Q-objects and decide if they're equivalent.

    Q objects don't have their own comparison methods defined.

    This function is intended to give an approximate comparison suitable
    for our purposes.

    Args:
        one, two (Q) Django Q Object

    Returns:
        (boolean) whether the objects match.
    """

    for item_one in one.children:
        if not is_child(item_one, two):
            return False

    for item_two in two.children:
        if not is_child(item_two, one):
            return False

    if one.connector != two.connector:
        return False

    if one.negated != two.negated:
        return False

    # no mismatches found. we will assume the two
    # Q objects are roughly equivalent.
    return True


def is_child(item, obj):
    """Test whether the given item is in the target Q object's children.

    Args:
        item (dict | tuple) a dict or tuple
        obj (Q) a Django Q object
    """
    test_dict = item
    if isinstance(item, tuple):
        test_dict = {item[0]: item[1]}

    test_tuple = item
    if isinstance(item, dict):
        test_tuple = (item.keys()[0], item.values()[0])

    # Q objects can have both tuples and dicts in their children.
    # So, we are comparing equivalent forms in case our test object is
    # formatted differently than the real version.
    if test_dict not in obj.children and test_tuple not in obj.children:
        return False
    return True


class ReportQueryHandlerTest(IamTestCase):
    """Test the report query handler functions."""

    def setUp(self):
        """Test setup."""
        self.mock_tag_key = FAKE.word()
        self.mock_view = Mock(
            spec=ReportView,
            report="mock",
            permission_classes=[Mock],
            provider="mock",
            serializer=Mock,
            query_handler=Mock,
            tag_handler=[
                Mock(
                    objects=Mock(
                        values=Mock(return_value=[{"key": self.mock_tag_key, "values": [FAKE.word(), FAKE.word()]}])
                    )
                )
            ],
        )

    def test_init(self):
        """Test that we can instantiate a minimal ReportQueryHandler."""
        params = self.mocked_query_params("", self.mock_view)
        rqh = create_test_handler(params)
        self.assertIsInstance(rqh, ReportQueryHandler)

    def test_init_w_dates(self):
        """Test that we can instantiate a ReportQueryHandler using start_date and end_date parameters."""
        dh = DateHelper()
        params = self.mocked_query_params(f"?start_date={dh.this_month_start}&end_date={dh.today}", self.mock_view)
        rqh = create_test_handler(params)
        self.assertIsInstance(rqh, ReportQueryHandler)

        expected_start = dh.this_month_start
        expected_end = dh.today

        self.assertEqual(rqh.start_datetime, expected_start)
        self.assertEqual(rqh.end_datetime, expected_end)

    def test_set_operator_specified_filters_and(self):
        """Test that AND/OR terms are correctly applied to param filters."""
        operator = "and"

        term = FAKE.word()
        first = FAKE.word()
        second = FAKE.word()
        operation = FAKE.word()

        url = f"?filter[time_scope_value]=-1&group_by[and:{term}]={first}&group_by[and:{term}]={second}"
        params = self.mocked_query_params(url, self.mock_view)

        mapper = {"filter": [{}], "filters": {term: {"field": term, "operation": operation}}}
        rqh = create_test_handler(params, mapper=mapper)
        output = rqh._set_operator_specified_filters(operator)
        self.assertIsNotNone(output)

        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field=term, operation=operation, parameter=second, logical_operator=operator),
                QueryFilter(field=term, operation=operation, parameter=first, logical_operator=operator),
            ]
        )
        assertSameQ(output, expected.compose())

    def test_set_operator_specified_filters_or(self):
        """Test that AND/OR terms are correctly applied to param filters."""
        operator = "or"

        term = FAKE.word()
        first = FAKE.word()
        second = FAKE.word()
        operation = FAKE.word()

        url = f"?filter[time_scope_value]=-1&group_by[or:{term}]={first}&group_by[or:{term}]={second}"
        params = self.mocked_query_params(url, self.mock_view)

        mapper = {"filter": [{}], "filters": {term: {"field": term, "operation": operation}}}
        rqh = create_test_handler(params, mapper=mapper)
        output = rqh._set_operator_specified_filters(operator)
        self.assertIsNotNone(output)

        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field=term, operation=operation, parameter=second, logical_operator=operator),
                QueryFilter(field=term, operation=operation, parameter=first, logical_operator=operator),
            ]
        )
        assertSameQ(output, expected.compose())

    def test_set_operator_specified_tag_filters_and(self):
        """Test that AND/OR terms are correctly applied to tag filters."""
        operator = "and"

        term = self.mock_tag_key
        first = FAKE.word()
        second = FAKE.word()
        operation = "icontains"

        url = (
            f"?filter[time_scope_value]=-1&"
            f"filter[and:tag:{term}]={first}&"
            f"filter[and:tag:{term}]={second}&"
            f"group_by[and:tag:{term}]={first}&"
            f"group_by[and:tag:{term}]={second}"
        )

        params = self.mocked_query_params(url, self.mock_view)
        mapper = {"filter": [{}], "filters": {term: {"field": term, "operation": operation}}}
        rqh = create_test_handler(params, mapper=mapper)
        output = rqh._set_operator_specified_tag_filters(QueryFilterCollection(), operator)

        self.assertIsNotNone(output)

        expected = QueryFilterCollection(
            filters=[
                QueryFilter(
                    table="tags", field=term, operation=operation, parameter=second, logical_operator=operator
                ),
                QueryFilter(table="tags", field=term, operation=operation, parameter=first, logical_operator=operator),
            ]
        )
        self.assertIsInstance(output, QueryFilterCollection)
        assertSameQ(output.compose(), expected.compose())

    def test_set_operator_specified_tag_filters_or(self):
        """Test that AND/OR terms are correctly applied to tag filters."""
        operator = "or"

        term = self.mock_tag_key
        first = FAKE.word()
        second = FAKE.word()
        operation = "icontains"

        url = (
            f"?filter[time_scope_value]=-1&"
            f"filter[or:tag:{term}]={first}&"
            f"filter[or:tag:{term}]={second}&"
            f"group_by[or:tag:{term}]={first}&"
            f"group_by[or:tag:{term}]={second}"
        )
        params = self.mocked_query_params(url, self.mock_view)
        mapper = {"filter": [{}], "filters": {term: {"field": term, "operation": operation}}}
        rqh = create_test_handler(params, mapper=mapper)
        output = rqh._set_operator_specified_tag_filters(QueryFilterCollection(), operator)
        self.assertIsNotNone(output)

        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field=term, operation=operation, parameter=second, logical_operator=operator),
                QueryFilter(field=term, operation=operation, parameter=first, logical_operator=operator),
            ]
        )
        self.assertIsInstance(output, QueryFilterCollection)
        assertSameQ(output.compose(), expected.compose())

    def test_set_access_filter_with_list(self):
        """
        Tests that when an access restriction, filters, and a filter list are passed in,
        the correct query filters are added
        """
        # create the elements needed to mock the query handler
        term = self.mock_tag_key
        operation = "icontains"
        params = self.mocked_query_params("", self.mock_view)
        mapper = {"filter": [{}], "filters": {term: {"field": term, "operation": operation}}}
        rqh = create_test_handler(params, mapper=mapper)
        # set filters and access to be used in function
        filters = QueryFilterCollection()
        access = ["589173575009"]
        filt = [
            {"field": "account_alias__account_alias", "operation": "icontains", "composition_key": "account_filter"},
            {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
        ]
        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field="account_alias__account_alias", operation="in", composition_key="account_filter"),
                QueryFilter(field="usage_account_id", operation="in", composition_key="account_filter"),
            ]
        )
        rqh.set_access_filters(access, filt, filters)
        self.assertIsInstance(filters, QueryFilterCollection)
        assertSameQ(filters.compose(), expected.compose())

    def test_set_access_filter_without_list(self):
        """
        Tests that when an access restriction, filters, and a filter list are passed in,
        the correct query filters are added
        """
        # create the elements needed to mock the query handler
        term = self.mock_tag_key
        operation = "icontains"
        params = self.mocked_query_params("", self.mock_view)
        mapper = {"filter": [{}], "filters": {term: {"field": term, "operation": operation}}}
        rqh = create_test_handler(params, mapper=mapper)
        # set filters and access to be used in function
        filters = QueryFilterCollection()
        access = ["589173575009"]
        filt = {"field": "account_alias__account_alias", "operation": "icontains", "composition_key": "account_filter"}
        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field="account_alias__account_alias", operation="in", composition_key="account_filter")
            ]
        )
        rqh.set_access_filters(access, filt, filters)
        self.assertIsInstance(filters, QueryFilterCollection)
        assertSameQ(filters.compose(), expected.compose())

    def test_percent_delta(self):
        """Test the percent delta method"""
        params = self.mocked_query_params("", self.mock_view)
        rqh = create_test_handler(params)
        pd = rqh._percent_delta(10, 1)
        self.assertEqual(pd, 900)

    def test_percent_delta_rounding(self):
        """Test the percent delta method with a b value that should round."""
        params = self.mocked_query_params("", self.mock_view)
        test_values = {0.0049: None, 0.0049999999999: None, 0.005: 3900}
        for k, v in test_values.items():
            with self.subTest():
                rqh = create_test_handler(params)
                pd = rqh._percent_delta(0.2, k)
                self.assertEqual(pd, v)

    def test_percent_delta_zero_division(self):
        """Test the percent delta method with a b value of zero"""
        params = self.mocked_query_params("", self.mock_view)
        rqh = create_test_handler(params)
        pd = rqh._percent_delta(10, 0)
        self.assertEqual(pd, None)

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
