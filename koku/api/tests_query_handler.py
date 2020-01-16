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
from api.iam.test.iam_test_case import IamTestCase
from api.provider.test import create_generic_provider
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.view import AWSInstanceTypeView
from api.report.test import FakeAWSCostData
from api.report.test.aws.helpers import AWSReportDataGenerator
from api.utils import DateHelper


class QueryHandlerTest(IamTestCase):
    """Tests the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()
        _, self.provider = create_generic_provider('AWS', self.headers)
        self.fake_aws = FakeAWSCostData(self.provider)
        self.generator = AWSReportDataGenerator(self.tenant)
        self.generator.add_data_to_tenant(self.fake_aws)

    def test_group_by_star_does_not_override_filters(self):
        """Test Group By star does not override filters, with example below.

        This is an expected response. Notice that the only region is eu-west-3
        {'data': [{'date': '2019-11-30', 'regions': []},
        {'date': '2019-12-01',
        'regions': [{'region': 'eu-west-3',
                        'services': [{'instance_types': [{'instance_type': 'r5.2xlarge',
                                                        'values': [{'cost': {'units': 'USD',
                                                                            'value': Decimal('2405.158832135')},
                                                                    'count': {'units': 'instances',
                                                                                'value': 1},
                                                                    'date': '2019-12-01',
                                                                    'derived_cost': {'units': 'USD',
                                                                                    'value': Decimal('0')},
                                                                    'infrastructure_cost': {'units': 'USD',
                                                                                            'value': Decimal('2186.508029214')}, # noqa
                                                                    'instance_type': 'r5.2xlarge',
                                                                    'markup_cost': {'units': 'USD',
                                                                                     'value': Decimal('218.650802921')},
                                                                    'region': 'eu-west-3',
                                                                    'service': 'AmazonEC2',
                                                                    'usage': {'units': 'Hrs',
                                                                                'value': Decimal('3807.000000000')}}]}],
                                    'service': 'AmazonEC2'}]}]},
        {'date': '2019-12-02', 'regions': []},
        {'date': '2019-12-03', 'regions': []},
        {'date': '2019-12-04', 'regions': []},
        {'date': '2019-12-05', 'regions': []},
        {'date': '2019-12-06', 'regions': []},
        {'date': '2019-12-07', 'regions': []},
        {'date': '2019-12-08', 'regions': []},
        {'date': '2019-12-09', 'regions': []}],

        """
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider), product='ec2')
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider, region='eu-west-3'), product='ec2')
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider, region='us-west-1'), product='ec2')

        # First Request:
        url = '?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        data = handler.execute_query()
        # Second Request:
        url2 = '?group_by[region]=eu-west-3&group_by[service]=AmazonEC2'
        query_params2 = self.mocked_query_params(url2, AWSInstanceTypeView)
        handler2 = AWSReportQueryHandler(query_params2)
        data2 = handler2.execute_query()
        # Assert the second request contains only eu-west-3 region
        for region_dict in data2['data']:
            # For each date, assert that the region is eu-west-3
            for list_item in region_dict['regions']:
                self.assertEquals('eu-west-3', list_item['region'])
        # Assert the first request contains only eu-west-3
        for region_dict in data['data']:
            # For each date, assert that the region is eu-west-3
            for list_item in region_dict['regions']:
                self.assertEquals('eu-west-3', list_item['region'])

    def test_filter_to_group_by(self):
        """Test the filter_to_group_by method."""
        url = '?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)

        self.assertEqual(['eu-west-3'], query_params._parameters['group_by']['region'])

    def test_filter_to_group_by_3(self):
        """Test what happens when user enters both group_by[service]=something AND group_by[service]=*."""
        url = '?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2&group_by[service]=*&filter[service]=AmazonEC2' # noqa
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)

        self.assertEqual(['eu-west-3'], query_params._parameters['group_by']['region'])
        self.assertEqual(['AmazonEC2'], query_params._parameters['group_by']['service'])

    def test_filter_to_group_by_star(self):
        """Test, when there are group_by star and no filters."""
        url = '?group_by[region]=*&group_by[service]=*'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)
        self.assertEqual(['*'], query_params._parameters['group_by']['region'])
        self.assertEqual(['*'], query_params._parameters['group_by']['service'])

    def test_two_filters_and_group_by_star(self):
        """
        Test two filters for the same category.

        For example, group_by[service]=*&filter[service]=X&filter[service]=Y
        """
        url = '?group_by[region]=*&filter[region]=eu-west-3&filter[region]=us-west-1'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)
        region_1_exists = False
        region_2_exists = False
        if 'eu-west-3' in query_params._parameters['group_by']['region']:
            region_1_exists = True
        if 'us-west-1' in query_params._parameters['group_by']['region']:
            region_2_exists = True
        # Both regions should be in the resulting group_by list.
        self.assertTrue(region_1_exists)
        self.assertTrue(region_2_exists)
