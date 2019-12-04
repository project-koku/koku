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
"""Test the Query Handler group_by[NAME]=*"""

from collections import Iterable

from django.db.models import Q
from django.test import TestCase
from faker import Faker

from api.query_filter import QueryFilter, QueryFilterCollection


class TestQueryHandlerGroupBy(TestCase):
    """Test when a group_by[X]=* is used, where X is a valid group_by option"""

    fake = Faker()

    def test_compilationError(self):
        self.assertEquals(1, 0)
    def test_filter_parameters_turn_into_group_by_parameters_when_group_by_is_star(self):
        
        actualValue = params._parameters.serializer.filter.parent._data['group_by']['service'][0]
        #assert that we started out with group_by[service]=*
        self.assertEqual(groupBy, '*')
        #assert that we started out with filter[service]=AmazonS3
        self.assertEqual(filter, 'AmazonS3')
        #ensure it's not a star anymore, or is empty..
        
        #TODO: call the method that fixes all that...

        #assert that groupBy isn't a star anymore
        self.assertNotEqual(groupBy, '*')
        #assert that group_by=AmazonS3
        self.assertEqual(groupBy, 'AmazonS3')
def test_response_structure(self):
        """
        Test that two requests (one using star, the other using no star) return the same response.
        
        Given a request, for example:
        ```
        GET
        api/reports/aws/storage/?group_by[region]=*
            &group_by[service]=AmazonS3, AmazonRDS
            &filter[region]=us-west-1
            &filter[region]=us-west-2
        ```
        
        The request should receive the SAME response as this:
        ```
        GET
        api/reports/aws/storage/?group_by[region]=us-west-1, us-west-2
            &group_by[service]=AmazonS3, AmazonRDS

        If the two responses are different, this test must fail.
        ```
        """

        self.assertEqual(firstResponse, secondResponse)