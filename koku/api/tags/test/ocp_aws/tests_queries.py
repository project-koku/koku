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
"""Test the OCP-on-AWS tag query handler."""
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.iam.test.iam_test_case import IamTestCase
from api.tags.ocp_aws.queries import OCPAWSTagQueryHandler
from api.tags.ocp_aws.view import OCPAWSTagView
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummary


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
        url = (
            "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"
        )  # noqa: E501
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
                OCPAWSCostLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("tags"))
                .values("tag_keys")
                .distinct()
                .all()
            )
            tag_keys = [tag.get("tag_keys") for tag in tag_keys]

        result = handler.get_tag_keys()
        self.assertEqual(sorted(result), sorted(tag_keys))
