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

"""Cost Usage Report process request class."""


# pylint: disable=too-few-public-methods
class CURProcessRequest:
    """Cost usage report request attributes.

    Effectively a struct for CUR processing a downloaded file.
    """

    def __init__(self):
        """Initialize new processing request."""
        self.schema_name = None
        self.report_path = None
        self.compression = None

    def __repr__(self):
        """Print attributes."""
        base = 'Processing request for file: {}, compression: {}, schema: {}'
        description = base.format(self.report_path, self.compression, self.schema_name)
        return description
