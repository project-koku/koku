#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWS Report Queries."""
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.view import AWSTagView
from api.utils import DateHelper
from reporting.models import AWSTagsSummary
from reporting.provider.aws.models import AWSTagsValues


class AWSTagQueryHandlerTest(IamTestCase):
    """Tests for the AWS report query handler."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_execute_query_for_account(self):
        """Test that the execute query runs properly with account query."""
        url = f"?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&filter[account]={self.fake.ean8()}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_slice_tag_values_list(self):
        """Test that long tag value lists are sliced."""
        slice_limit = 2
        url = "?filter[time_scope_value]=-1"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        handler.execute_query()
        handler._slice_tag_values_list(n=slice_limit)
        for entry in handler.query_data:
            values = entry.get("values")
            if len(values) > slice_limit:
                self.assertIn("more...", values[-1])

    def test_get_tags_for_key_filter(self):
        """Test that the execute query runs properly with key query."""
        key = "version"
        url = f"?filter[key]={key}"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = AWSTagsSummary.objects.filter(key__contains=key).values("values").distinct().all()
            tag_values = tags[0].get("values")
        expected = {"key": key, "values": tag_values}
        result = handler.get_tags()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_get_tag_values_for_value_filter(self):
        """Test that the execute query runs properly with value query."""
        key = "version"
        value = "prod"
        url = f"?filter[value]={value}"
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        handler.key = key
        with tenant_context(self.tenant):
            tags = AWSTagsValues.objects.filter(key__exact=key, value=value).values("value").distinct().all()
            tag_values = [tag.get("value") for tag in tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_get_tag_values_for_value_filter_partial_match(self):
        """Test that the execute query runs properly with value query."""
        key = "version"
        value = "a"
        url = f"/version/?filter[value]={value}"
        query_params = self.mocked_query_params(url, AWSTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = AWSTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = (
                AWSTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            tag_values = [tag.get("value") for tag in tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))
