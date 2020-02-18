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
"""Test the Report Queries."""
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.provider.test import create_generic_provider
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from api.utils import DateHelper
from reporting.models import OCPUsageLineItemDailySummary


class OCPTagQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        _, self.provider = create_generic_provider(Provider.PROVIDER_OCP, self.headers)
        OCPReportDataGenerator(self.tenant, self.provider).add_data_to_tenant()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_1_month_parameters_only_keys(self):
        """Test that the execute query runs properly with 1 month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&key_only=True"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_get_tag_keys_filter_true(self):
        """Test that not all tag keys are returned with a filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            usage_tag_keys = (
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("pod_labels"))
                .values("tag_keys")
                .distinct()
                .all()
            )

            usage_tag_keys = [tag.get("tag_keys") for tag in usage_tag_keys]

            storage_tag_keys = (
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("volume_labels"))
                .values("tag_keys")
                .distinct()
                .all()
            )
            storage_tag_keys = [tag.get("tag_keys") for tag in storage_tag_keys]
            tag_keys = list(set(usage_tag_keys + storage_tag_keys))

        result = handler.get_tag_keys(filters=True)
        self.assertNotEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_keys_filter_false(self):
        """Test that all tag keys are returned with no filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            usage_tag_keys = (
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("pod_labels"))
                .values("tag_keys")
                .distinct()
                .all()
            )

            usage_tag_keys = [tag.get("tag_keys") for tag in usage_tag_keys]

            storage_tag_keys = (
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("volume_labels"))
                .values("tag_keys")
                .distinct()
                .all()
            )
            storage_tag_keys = [tag.get("tag_keys") for tag in storage_tag_keys]
            tag_keys = list(set(usage_tag_keys + storage_tag_keys))

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_type_filter_pod(self):
        """Test that all usage tags are returned with pod type filter."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly&filter[type]=pod"
        )  # noqa: E501
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            usage_tag_keys = (
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("pod_labels"))
                .values("tag_keys")
                .distinct()
                .all()
            )

            usage_tag_keys = [tag.get("tag_keys") for tag in usage_tag_keys]
            tag_keys = usage_tag_keys

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_type_filter_storage(self):
        """Test that all storage tags are returned with storage type filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly&filter[type]=storage"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            storage_tag_keys = (
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("volume_labels"))
                .values("tag_keys")
                .distinct()
                .all()
            )
            storage_tag_keys = [tag.get("tag_keys") for tag in storage_tag_keys]
            tag_keys = storage_tag_keys

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))
