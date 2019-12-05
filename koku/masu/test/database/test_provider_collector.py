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

"""Test the ProviderDBAccessor utility object."""
import uuid

from masu.database.provider_collector import ProviderCollector
from masu.test import MasuTestCase


class ProviderQueryTest(MasuTestCase):
    """Test Cases for the ProviderDBAccessor object."""

    def test_get_uuids(self):
        """Test getting all uuids."""
        collector = ProviderCollector()
        providers = collector.get_providers()
        test_provider_found = False
        for provider in providers:
            if uuid.UUID(self.aws_provider_uuid) == provider.uuid:
                test_provider_found = True
        self.assertTrue(test_provider_found)
