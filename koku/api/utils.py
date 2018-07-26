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

"""Unit conversion util functions."""

import pint


class UnitConverter:
    """Utility class to do unit conversion."""\

    def __init__(self):
        """Initialize the UnitConverter."""
        self.unit_registry = pint.UnitRegistry()
        self.Quantity = self.unit_registry.Quantity

    def convert_quantity(self, value, from_unit, to_unit):
        """Convert a quantity between comparable units.

        Args:
            value (Any numeric type): The magnitude of the quantity
            from_unit (str): The starting unit to convert from
            to_unit (str): The ending unit to conver to

        Returns:
            (pint.Quantity): A quantity with both magnitude and unit

        Example:

            >>> uc = UnitConverter()
            >>> result = uc.covert_quantity(1.2, 'gigabyte', 'byte')
            >>> result
            <Quantity(1200000000.0, 'byte')>
            >>> print(result.magnitude)
            1200000000.0
            >>> print(result.units)
            byte

        """
        return self.Quantity(value, from_unit).to(to_unit)
