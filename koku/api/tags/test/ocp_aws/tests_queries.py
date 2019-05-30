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
from api.report.test.ocp_aws.helpers import OCPAWSReportDataGenerator
from api.tags.ocp_aws.queries import OCPAWSTagQueryHandler
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummary


# pylint: disable=no-member
class OCPAWSTagQueryHandlerTest(IamTestCase):
    """Tests for the OCP-on-AWS tag query handler."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.dh = DateHelper()
        generator = OCPAWSReportDataGenerator(self.tenant)
        generator.add_data_to_tenant()
        generator.add_aws_data_to_tenant()

    def test_no_parameters(self):
        """Test that the execute_query() succeeds with no parameters."""
        handler = OCPAWSTagQueryHandler({}, '', self.tenant, **{})

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_10_day(self):
        """Test that the execute_query() succeeds with 10 day parameters."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -10,
                                   'time_scope_units': 'day'},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-10&' + \
                       'filter[time_scope_units]=day&'
        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_30_day(self):
        """Test that execute_query() succeeds with 30 day parameters."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -30,
                                   'time_scope_units': 'day'},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-30&' + \
                       'filter[time_scope_units]=day&'
        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -30)

    def test_10_day_only_keys(self):
        """Test that execute_query() succeeds with 10 day parameters, keys-only."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -10,
                                   'time_scope_units': 'day',
                                   'key_only': True}
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-10&' + \
                       'filter[time_scope_units]=day&' + \
                       'key_only=True'
        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_1_month(self):
        """Test that execute_query() succeeds with 1-month parameters."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-1&' + \
                       'filter[time_scope_units]=month&'
        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -1)

    def test_last_month(self):
        """Test that execute_query() succeeds with last-month parameters."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -2,
                                   'time_scope_units': 'month'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-2&' + \
                       'filter[time_scope_units]=month&'
        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -2)

    def test_specific_account(self):
        """Test that execute_query() succeeds with account parameter."""
        account = self.fake.ean8()
        query_params = {'filter': {'account': account},
                        }
        query_string = '?filter[account]={}'.format(account)

        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)

    def test_get_tag_keys(self):
        """Test that all OCP-on-AWS tag keys are returned."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -2,
                                   'time_scope_units': 'month'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-2&' + \
                       'filter[time_scope_units]=month&'
        handler = OCPAWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        with tenant_context(self.tenant):
            tag_keys = OCPAWSCostLineItemDailySummary.objects\
                .annotate(tag_keys=JSONBObjectKeys('tags'))\
                .values('tag_keys')\
                .distinct()\
                .all()
            tag_keys = [tag.get('tag_keys') for tag in tag_keys]

        result = handler.get_tag_keys()
        self.assertEqual(sorted(result), sorted(tag_keys))
