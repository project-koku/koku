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

from masu.database.provider_collector import ProviderCollector
from tests import MasuTestCase


class ProviderQueryTest(MasuTestCase):
    """Test Cases for the ProviderDBAccessor object."""

    def test_initializer(self):
        """Test Initializer"""
        collector = ProviderCollector()
        self.assertIsNotNone(collector._session)
        collector.close_session()

    def test_get_uuids(self):
        """Test getting all uuids."""
        collector = ProviderCollector()
        providers = collector.get_providers()
        test_provider_found = False
        for provider in providers:
            if '6e212746-484a-40cd-bba0-09a19d132d64' in provider.uuid:
                test_provider_found = True
        self.assertTrue(test_provider_found)
        collector.close_session()
