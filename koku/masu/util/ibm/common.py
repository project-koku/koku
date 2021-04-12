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
"""IBM utility functions and vars."""
import hashlib
import logging

LOG = logging.getLogger(__name__)


def generate_etag(param):
    """Generate etag for IBM Cloud report."""
    return hashlib.md5(str(param).encode()).hexdigest()


def generate_assembly_id(params):
    """Generate assembly id for IBM Cloud report."""
    return ":".join([str(param) for param in params if param])
