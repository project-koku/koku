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
"""Masu Processor Exceptions."""


class MasuProcessingError(Exception):
    """Masu Processing Error."""


class MasuProviderError(Exception):
    """Masu Provider Error."""


class MasuConfigurationError(Exception):
    """Masu Configuration Error."""


class CURAccountsInterfaceError(Exception):
    """CURAccountsInterface error."""


class HasherError(Exception):
    """Hasher Utility class error."""
