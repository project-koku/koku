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
from api.report.test import FakeQueryParameters
from api.report.test.azure.helpers import AzureReportDataGenerator
from api.tags.azure.queries import AzureTagQueryHandler
from reporting.models import AzureCostEntryLineItemDailySummary


class AzureTagQueryHandlerTest(IamTestCase):
    """Tests for the Azure report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        AzureReportDataGenerator(self.tenant).add_data_to_tenant()

    def tearDown(self):
        """Test case tear-down."""
        gen = AzureReportDataGenerator(self.tenant)
        gen.remove_data_from_tenant()
        gen.remove_data_from_reporting_common()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        # '?
        handler = AzureTagQueryHandler(FakeQueryParameters({}, tenant=self.tenant).mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        # '?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -10,
                             'time_scope_units': 'day'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        # '?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -30,
                             'time_scope_units': 'day'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        # '?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -10,
                             'time_scope_units': 'day'},
                  'key_only': True}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -2,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -2)

    def test_execute_query_for_project(self):
        """Test that the execute query runs properly with project query."""
        subscription_guid = None
        with tenant_context(self.tenant):
            obj = AzureCostEntryLineItemDailySummary.objects\
                .values('subscription_guid')\
                .first()
            subscription_guid = obj.get('subscription_guid')

        # '?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&filter[subscription_guid]=some_uuid'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -10,
                             'time_scope_units': 'day',
                             'subscription_guid': subscription_guid}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_get_tag_keys_filter_true(self):
        """Test that not all tag keys are returned with a filter."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -2,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)

        tag_keys = set()
        with tenant_context(self.tenant):
            tags = AzureCostEntryLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('tags'))\
                .values('tags')\
                .distinct()\
                .all()

            for tag in tags:
                for key in tag.get('tags').keys():
                    tag_keys.add(key)

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(list(tag_keys)))

    def test_get_tag_keys_filter_false(self):
        """Test that all tag keys are returned with no filter."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -2,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)

        tag_keys = set()
        with tenant_context(self.tenant):
            tags = AzureCostEntryLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('tags'))\
                .values('tags')\
                .distinct()\
                .all()

            for tag in tags:
                for key in tag.get('tags').keys():
                    tag_keys.add(key)

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(list(tag_keys)))
