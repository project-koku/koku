#
# Copyright 2020 Red Hat, Inc.
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
"""Test the AWS Report Queries."""
from datetime import timedelta

from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.organizations.aws.queries import AWSOrgQueryHandler
from api.organizations.aws.view import AWSOrgView
from api.organizations.test.utils import GenerateOrgTestData
from api.utils import DateHelper


class AWSOrgQueryHandlerTest(IamTestCase):
    """Tests for the AWS report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        self.generate_data = GenerateOrgTestData(self.schema_name)

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        self.generate_data.insert_data()
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)
        self.assertIsNotNone(query_output["data"][0].get("org_unit_id"))
        self.assertIsNone(query_output["data"][0].get("sub_orgs"))
        self.assertIsNone(query_output["data"][0].get("accounts"))

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_exclude_filters_for_dates(self):
        """Test that the execute query runs properly with two month query."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        deleted_before = (handler.start_datetime - timedelta(1)).strftime("%Y-%m-%d")
        deleted_after = (handler.start_datetime + timedelta(1)).strftime("%Y-%m-%d")
        # If a node was deleted the day before your date range it doesn’t appear.
        # Also if it was deleted a day after your date range it does appear.
        self.generate_data.data_list = [
            {
                "ou": {"Name": "big-ou", "Id": "big-ou0"},
                "path": "r-id&big-ou0",
                "level": 1,
                "account": None,
                "deleted": deleted_before,
            },
            {
                "ou": {"Name": "big-ou1", "Id": "big-ou1"},
                "path": "r-id&big-ou1",
                "level": 1,
                "account": None,
                "created": handler.start_datetime,
                "deleted": deleted_after,
            },
        ]
        self.generate_data.insert_data()
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(len(query_output.get("data")), 1)
