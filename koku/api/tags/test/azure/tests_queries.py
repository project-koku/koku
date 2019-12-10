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
"""Test the common tag query function."""
from api.iam.test.iam_test_case import IamTestCase
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.azure.view import AzureTagView


class AzureTagQueryHandlerTest(IamTestCase):
    """Tests for the AzureTagQueryHandler."""

    def test_merge_tags(self):
        """Test the _merge_tags functionality."""
        url = '?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily'
        query_params = self.mocked_query_params(url, AzureTagView)

        tagHandler = AzureTagQueryHandler(query_params)

        # Test no source type
        source = {}
        tag_keys = [{'ms-resource-usage': 'azure-cloud-shell'},
                    {'project': 'p1'}, {'cost': 'management', 'project': 'p2'}]
        expected = [{'key': 'ms-resource-usage', 'values': ['azure-cloud-shell']},
                    {'key': 'project', 'values': ['p1', 'p2']},
                    {'key': 'cost', 'values': ['management']}]
        merged_data = tagHandler._merge_tags(source, tag_keys)
        self.assertEqual(merged_data, expected)

        # Test with source type
        source = {'type': 'storage'}
        merged_data = tagHandler._merge_tags(source, tag_keys)
        expected = [{'key': 'ms-resource-usage', 'values': ['azure-cloud-shell'], 'type': 'storage'},
                    {'key': 'project', 'values': ['p1', 'p2'], 'type': 'storage'},
                    {'key': 'cost', 'values': ['management'], 'type': 'storage'}]
        self.assertEqual(merged_data, expected)
