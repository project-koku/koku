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

"""Blueprint register for APIs."""

from flask import Blueprint

from masu.api.download import API_V1_ROUTES as download_routes_v1
from masu.api.expired_data import API_V1_ROUTES as expired_data_v1
from masu.api.notification import API_V1_ROUTES as notification_routes_v1
from masu.api.status import API_V1_ROUTES as status_routes_v1
from masu.util.blueprint import add_routes_to_blueprint

# pylint: disable=invalid-name
api_v1 = Blueprint('api', __name__, url_prefix='/api/v1')

add_routes_to_blueprint(api_v1, status_routes_v1)
add_routes_to_blueprint(api_v1, expired_data_v1)
add_routes_to_blueprint(api_v1, download_routes_v1)
add_routes_to_blueprint(api_v1, notification_routes_v1)
