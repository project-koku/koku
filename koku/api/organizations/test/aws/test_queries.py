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
import datetime

from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.organizations.aws.queries import AWSOrgQueryHandler
from api.organizations.aws.view import AWSOrgView
from api.utils import DateHelper
from reporting.provider.aws.models import AWSOrganizationalUnit


class AWSOrgQueryHandlerTest(IamTestCase):
    """Tests for the AWS report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        with tenant_context(self.tenant):
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
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_exclude_filters_for_dates(self):
        """Test that the execute query runs properly with two month query."""
        url = "?"
        excluded_ou = "OU_004"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        for data in query_output.get("data"):
            self.assertNotEqual(data["org_unit_id"], excluded_ou)

    def test_data_created_on_enddate_not_excluded(self):
        """Test that data created on end_datetime is not excluded."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        end_date = handler.end_datetime
        with tenant_context(self.tenant):
            org_unit_objs = AWSOrganizationalUnit.objects.update(created_timestamp=end_date)
            self.assertNotEqual(org_unit_objs, 0)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertNotEqual(data, [])
        self.assertGreater(len(data), 1)
        # Test that accounts show up
        accounts_check = False
        for ou in data:
            if ou.get("org_unit_id") == "OU_001":
                self.assertNotEqual(ou.get("accounts"), [])
                accounts_check = True
        self.assertTrue(accounts_check)

    def test_data_created_after_enddate_is_excluded(self):
        """Test that data created after end_datetime is excluded."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSOrgView)
        handler = AWSOrgQueryHandler(query_params)
        end_date = handler.end_datetime
        exclude_date = end_date + datetime.timedelta(days=1)
        with tenant_context(self.tenant):
            org_unit_objs = AWSOrganizationalUnit.objects.update(created_timestamp=exclude_date)
            self.assertNotEqual(org_unit_objs, 0)
        with tenant_context(self.tenant):
            query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertEqual(data, [])
