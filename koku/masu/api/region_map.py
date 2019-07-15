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

"""View endpoint for updating region mapping."""

from flask import jsonify

from masu.util.aws.region_map import update_region_mapping
from masu.util.blueprint import application_route

API_V1_ROUTES = {}


@application_route('/regionmap/', API_V1_ROUTES, methods=('GET',))
def update_region_map():
    """Return download file async task ID."""
    return jsonify(update_region_mapping())
