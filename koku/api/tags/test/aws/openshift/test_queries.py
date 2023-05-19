#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP-on-AWS tag query handler."""
from django_tenants.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.iam.test.iam_test_case import IamTestCase
from api.tags.aws.openshift.queries import OCPAWSTagQueryHandler
from api.tags.aws.openshift.view import OCPAWSTagView
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummaryP
from reporting.models import OCPAWSTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSTagsValues


class OCPAWSTagQueryHandlerTest(IamTestCase):
    """Tests for the OCP-on-AWS tag query handler."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.dh = DateHelper()

    def test_no_parameters(self):
        """Test that the execute_query() succeeds with no parameters."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_10_day(self):
        """Test that the execute_query() succeeds with 10 day parameters."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_30_day(self):
        """Test that execute_query() succeeds with 30 day parameters."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -30)

    def test_10_day_only_keys(self):
        """Test that execute_query() succeeds with 10 day parameters, keys-only."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_1_month(self):
        """Test that execute_query() succeeds with 1-month parameters."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_last_month(self):
        """Test that execute_query() succeeds with last-month parameters."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_specific_account(self):
        """Test that execute_query() succeeds with account parameter."""
        url = f"?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&filter[account]={str(self.fake.ean8())}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_get_tag_keys(self):
        """Test that all OCP-on-AWS tag keys are returned."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            tag_keys = (
                OCPAWSCostLineItemDailySummaryP.objects.annotate(tag_keys=JSONBObjectKeys("tags"))
                .values("tag_keys")
                .distinct()
                .all()
            )
            tag_keys = [tag.get("tag_keys") for tag in tag_keys]

        result = handler.get_tag_keys()
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_cluster_filter(self):
        """Test that tags from a cluster are returned with the cluster filter."""
        url = "?filter[cluster]=OCP-on-AWS"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            tag_keys = (
                OCPAWSTagsSummary.objects.filter(report_period__cluster_id__contains="OCP-on-AWS")
                .values("key")
                .distinct()
                .all()
            )
            tag_keys = [tag.get("key") for tag in tag_keys]

        result = handler.get_tag_keys()
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_execute_query_for_key_filter(self):
        """Test that the execute query runs properly with key query."""
        key = "app"
        url = f"?filter[key]={key}"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = OCPAWSTagsSummary.objects.filter(key__exact=key).values("values").distinct().first()
            expected_tag_values = tags.get("values")
        results = {r.get("key"): r.get("values") for r in handler.get_tags()}
        self.assertIn(key, results)
        self.assertEqual(sorted(results[key]), sorted(expected_tag_values))

    def test_execute_query_for_value_filter(self):
        """Test that the execute query runs properly with value query."""
        key = "app"
        with tenant_context(self.tenant):
            tag = OCPAWSTagsValues.objects.filter(key__exact=key).values("value").first()
        value = tag.get("value")
        url = f"?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        handler.key = key
        with tenant_context(self.tenant):
            tags = OCPAWSTagsValues.objects.filter(key__exact=key, value=value).values("value").distinct().all()
            tag_values = [tag.get("value") for tag in tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_execute_query_for_value_filter_partial_match(self):
        """Test that the execute query runs properly with value query."""
        key = "app"
        with tenant_context(self.tenant):
            tag = OCPAWSTagsValues.objects.filter(key__exact=key).values("value").first()
        value = tag.get("value")[0]  # get first letter of value
        url = f"/{key}/?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPAWSTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = OCPAWSTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = (
                OCPAWSTagsValues.objects.filter(key__exact=key, value__icontains=value)
                .values("value")
                .distinct()
                .all()
            )
            tag_values = [tag.get("value") for tag in tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))
