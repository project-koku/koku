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
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.iam.test.iam_test_case import IamTestCase
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.azure.view import AzureTagView
from reporting.models import AzureCostEntryLineItemDailySummary
from reporting.models import AzureTagsSummary
from reporting.provider.azure.models import AzureTagsValues


class AzureTagQueryHandlerTest(IamTestCase):
    """Tests for the Azure report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        url = "?"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        url = "?filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_execute_query_for_project(self):
        """Test that the execute query runs properly with project query."""
        subscription_guid = None
        with tenant_context(self.tenant):
            obj = AzureCostEntryLineItemDailySummary.objects.values("subscription_guid").first()
            subscription_guid = obj.get("subscription_guid")

        url = f"?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&filter[subscription_guid]={subscription_guid}"  # noqa: E501
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_get_tag_keys_filter_true(self):
        """Test that not all tag keys are returned with a filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)

        tag_keys = set()
        with tenant_context(self.tenant):
            tags = (
                AzureCostEntryLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("tags"))
                .values("tags")
                .distinct()
                .all()
            )

            for tag in tags:
                for key in tag.get("tags").keys():
                    tag_keys.add(key)

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(list(tag_keys)))

    def test_get_tag_keys_filter_false(self):
        """Test that all tag keys are returned with no filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)

        tag_keys = set()
        with tenant_context(self.tenant):
            tags = (
                AzureCostEntryLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("tags"))
                .values("tags")
                .distinct()
                .all()
            )

            for tag in tags:
                for key in tag.get("tags").keys():
                    tag_keys.add(key)

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(list(tag_keys)))

    def test_get_tags_for_key_filter(self):
        """Test that get tags runs properly with key query."""
        key = "version"
        url = f"?filter[key]={key}"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = AzureTagsSummary.objects.filter(key__contains=key).values("values").distinct().all()
            tag_values = tags[0].get("values")
        expected = {"key": key, "values": tag_values}
        result = handler.get_tags()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_get_tag_values_for_value_filter(self):
        """Test that get tag values runs properly with value query."""
        key = "version"
        value = "Andromeda"
        url = f"?filter[value]={value}"
        query_params = self.mocked_query_params(url, AzureTagView)
        handler = AzureTagQueryHandler(query_params)
        handler.key = key
        with tenant_context(self.tenant):
            tags = AzureTagsValues.objects.filter(key__exact=key, value=value).values("value").distinct().all()
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
        query_params = self.mocked_query_params(url, AzureTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = AzureTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = (
                AzureTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            tag_values = [tag.get("value") for tag in tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))
