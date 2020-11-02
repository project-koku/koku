#
# Copyright 2020 Red Hat, Inc.
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
"""Forecast unit tests."""
from unittest import TestCase

from forecast import Forecast


class ForecastTest(TestCase):
    """Tests the Forecast class."""

    def test_constructor(self):
        """Test the constructor."""
        params = {}
        instance = Forecast(params)
        self.assertIsInstance(instance, Forecast)

    def test_predict(self):
        """Test that predict() returns expected values."""
        expected = [1, 2, 3, 4, 5]
        params = {}
        instance = Forecast(params)
        results = instance.predict()
        self.assertEqual([item.get("value") for item in results], expected)
