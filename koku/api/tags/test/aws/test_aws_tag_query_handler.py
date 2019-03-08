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
"""Test the AWS Report Queries."""
from api.iam.test.iam_test_case import IamTestCase
from api.tags.aws.aws_tag_query_handler import AWSTagQueryHandler
from api.utils import DateHelper


class AWSTagQueryHandlerTest(IamTestCase):
    """Tests for the AWS report query handler."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        query_params = {}
        handler = AWSTagQueryHandler(
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
        handler = AWSTagQueryHandler(
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
        handler = AWSTagQueryHandler(
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
        handler = AWSTagQueryHandler(
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
        handler = AWSTagQueryHandler(
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
        handler = AWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'month')
        self.assertEqual(handler.time_scope_value, -2)

    def test_execute_query_for_account(self):
        """Test that the execute query runs properly with account query."""
        account = IamTestCase.fake.ean8()
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -10,
                                   'time_scope_units': 'day',
                                   'account': account},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-10&' + \
                       'filter[time_scope_units]=day&' + \
                       'filter[account]={}'.format(account)

        handler = AWSTagQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{}
        )

        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertEqual(handler.time_scope_units, 'day')
        self.assertEqual(handler.time_scope_value, -10)
