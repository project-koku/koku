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
"""Test the API utils module."""

import random

import pint
from django.test import TestCase
from pint.errors import UndefinedUnitError

from api.utils import UnitConverter


class APIUtilsUnitConverterTest(TestCase):
    """Tests against the API utils."""

    @classmethod
    def setUpClass(cls):
        """Set up for test class."""
        super().setUpClass()
        cls.converter = UnitConverter()

    def test_initializer(self):
        """Test that the UnitConverter starts properly."""
        self.assertIsInstance(
            self.converter.unit_registry,
            pint.registry.UnitRegistry
        )

        self.assertTrue(hasattr(self.converter.Quantity, 'units'))
        self.assertTrue(hasattr(self.converter.Quantity, 'magnitude'))

    def test_validate_unit_success(self):
        """Test that unit validation succeeds with known units."""
        unit = 'GB'
        result = self.converter.validate_unit(unit)
        self.assertEqual(unit, result)

        unit = 'Hrs'
        result = self.converter.validate_unit(unit)
        self.assertEqual(unit.lower(), result)

    def test_validate_unit_failure(self):
        """Test that an exception is thrown with an invalid unit."""
        unit = 'Gigglebots'

        with self.assertRaises(UndefinedUnitError):
            self.converter.validate_unit(unit)

    def test_unit_converter(self):
        """Test that unit conversion succeeds."""
        value = random.randint(1, 9)
        from_unit = 'gigabyte'
        to_unit = 'byte'

        expected_value = value * 1E9

        result = self.converter.convert_quantity(value, from_unit, to_unit)

        self.assertEqual(result.units, to_unit)
        self.assertEqual(result.magnitude, expected_value)
