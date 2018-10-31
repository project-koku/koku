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
"""Test the OCPReportQueryHandler base class."""

from api.iam.test.iam_test_case import IamTestCase
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.utils import DateHelper


class OCPReportQueryHandlerTest(IamTestCase):
    """Tests for the report query handler."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

        cls.data_generator = OCPReportDataGenerator(cls.tenant)

        cls.this_month_filter = {'usage_start__gte': cls.dh.this_month_start}
        cls.ten_day_filter = {'usage_start__gte': cls.dh.n_days_ago(cls.dh.today, 10)}
        cls.thirty_day_filter = {'usage_start__gte': cls.dh.n_days_ago(cls.dh.today, 30)}
        cls.last_month_filter = {'usage_start__gte': cls.dh.last_month_start,
                                 'usage_end__lte': cls.dh.last_month_end}

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.data_generator.add_data_to_tenant()
