#
# Copyright 2021 Red Hat, Inc.
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
"""Django model mixins and utilities."""


class RunTextFieldValidators:
    """
    Mixin to run all field validators on a save method call
    This mixin should appear BEFORE Model.
    """

    def save(self, *args, **kwargs):
        """
        For all fields, run any default and specified validators before calling save
        """
        for f in (
            c for c in self._meta.get_fields() if hasattr(self, c.name) and c.get_internal_type() == "TextField"
        ):
            val = getattr(self, f.name)
            if val is not None:
                val = str(val)
            f.run_validators(val)

        super().save(*args, **kwargs)
