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
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AzureTagView)

        tagHandler = AzureTagQueryHandler(query_params)

        # Test no source type
        final = []
        source = {}
        tag_keys = {"ms-resource-usage": ["azure-cloud-shell"], "project": ["p1", "p2"], "cost": ["management"]}
        expected_1 = [
            {"key": "ms-resource-usage", "values": ["azure-cloud-shell"]},
            {"key": "project", "values": ["p1", "p2"]},
            {"key": "cost", "values": ["management"]},
        ]
        tagHandler.append_to_final_data_without_type(final, tag_keys)
        self.assertEqual(final, expected_1)

        # Test with source type
        final = []
        source = {"type": "storage"}
        tagHandler.append_to_final_data_with_type(final, tag_keys, source)
        expected_2 = [
            {"key": "ms-resource-usage", "values": ["azure-cloud-shell"], "type": "storage"},
            {"key": "project", "values": ["p1", "p2"], "type": "storage"},
            {"key": "cost", "values": ["management"], "type": "storage"},
        ]
        self.assertEqual(final, expected_2)

        final = []
        tagHandler.append_to_final_data_without_type(final, tag_keys)
        tagHandler.append_to_final_data_with_type(final, tag_keys, source)

        expected_3 = [
            {"key": "ms-resource-usage", "values": ["azure-cloud-shell"]},
            {"key": "project", "values": ["p1", "p2"]},
            {"key": "cost", "values": ["management"]},
            {"key": "ms-resource-usage", "values": ["azure-cloud-shell"], "type": "storage"},
            {"key": "project", "values": ["p1", "p2"], "type": "storage"},
            {"key": "cost", "values": ["management"], "type": "storage"},
        ]

        self.assertEqual(final, expected_3)
