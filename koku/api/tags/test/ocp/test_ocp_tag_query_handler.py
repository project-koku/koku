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
from django.db.models import Count
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.iam.test.iam_test_case import IamTestCase
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.tags.ocp.ocp_tag_query_handler import OCPTagQueryHandler
from api.utils import DateHelper
from reporting.models import OCPStorageLineItemDailySummary, OCPUsageLineItemDailySummary


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
        OCPReportDataGenerator(self.tenant).add_data_to_tenant()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        query_params = {}
        handler = OCPTagQueryHandler(
            query_params,
            '',
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -10,
                                   'time_scope_units': 'day'},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-10&' + \
                       'filter[time_scope_units]=day&'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -30,
                                   'time_scope_units': 'day'},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-30&' + \
                       'filter[time_scope_units]=day&'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -10,
                                   'time_scope_units': 'day',
                                   'key_only': True}
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-10&' + \
                       'filter[time_scope_units]=day&' + \
                       'key_only=True'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-1&' + \
                       'filter[time_scope_units]=month&'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -2,
                                   'time_scope_units': 'month'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-2&' + \
                       'filter[time_scope_units]=month&'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -2)

    def test_execute_query_for_project(self):
        """Test that the execute query runs properly with project query."""
        namespace = None
        with tenant_context(self.tenant):
            namespace_obj = OCPUsageLineItemDailySummary.objects\
                .values('namespace')\
                .first()
            namespace = namespace_obj.get('namespace')

        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -10,
                                   'time_scope_units': 'day',
                                   'project': namespace},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-10&' + \
                       'filter[time_scope_units]=day&' + \
                       'filter[project]={}'.format(namespace)

        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_get_tag_keys_filter_true(self):
        """Test that not all tag keys are returned with a filter."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month',
                                   'tag:environment': 'prod'}
                        }
        handler = OCPTagQueryHandler(
            query_params,
            None,
            self.tenant,
            **{}
        )

        with tenant_context(self.tenant):
            usage_tag_keys = OCPUsageLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('pod_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()

            usage_tag_keys = [tag.get('tag_keys') for tag in usage_tag_keys]

            storage_tag_keys = OCPStorageLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('volume_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()
            storage_tag_keys = [tag.get('tag_keys') for tag in storage_tag_keys]
            tag_keys = usage_tag_keys + storage_tag_keys

        result = handler.get_tag_keys(filters=True)
        self.assertNotEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_keys_filter_false(self):
        """Test that all tag keys are returned with no filter."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month'},
                        }
        handler = OCPTagQueryHandler(
            query_params,
            None,
            self.tenant,
            **{}
        )

        with tenant_context(self.tenant):
            usage_tag_keys = OCPUsageLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('pod_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()

            usage_tag_keys = [tag.get('tag_keys') for tag in usage_tag_keys]

            storage_tag_keys = OCPStorageLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('volume_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()
            storage_tag_keys = [tag.get('tag_keys') for tag in storage_tag_keys]
            tag_keys = usage_tag_keys + storage_tag_keys

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_type_filter_pod(self):
        """Test that all usage tags are returned with pod type filter."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -2,
                                   'time_scope_units': 'month',
                                   'type': 'pod'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-2&' + \
                       'filter[time_scope_units]=month&' + \
                       'filter[type]=pod&'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        with tenant_context(self.tenant):
            usage_tag_keys = OCPUsageLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('pod_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()

            usage_tag_keys = [tag.get('tag_keys') for tag in usage_tag_keys]
            tag_keys = usage_tag_keys

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_type_filter_storage(self):
        """Test that all storage tags are returned with storage type filter."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -2,
                                   'time_scope_units': 'month',
                                   'type': 'storage'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-2&' + \
                       'filter[time_scope_units]=month&' + \
                       'filter[type]=storage&'
        handler = OCPTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        with tenant_context(self.tenant):
            storage_tag_keys = OCPStorageLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('volume_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()
            storage_tag_keys = [tag.get('tag_keys') for tag in storage_tag_keys]
            tag_keys = storage_tag_keys

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))
