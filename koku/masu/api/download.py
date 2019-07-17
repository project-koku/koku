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

"""View for temporary force download endpoint."""

import logging

from flask import jsonify

from masu.celery.tasks import check_report_updates
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}


@application_route('/download/', API_V1_ROUTES, methods=('GET',))
def download_report():
    """Return download file async task ID."""
    async_download_result = check_report_updates.delay()
    return jsonify({'Download Request Task ID': str(async_download_result)})
