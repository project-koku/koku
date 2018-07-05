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
from flask.views import View


from masu.processor.orchestrator import Orchestrator

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class DownloadView(View):
    """A view that returns download file list JSON."""

    def dispatch_request(self):
        """Packages response for class-based view."""
        orchestrator = Orchestrator()
        orchestrator.prepare()
        return jsonify({'message': 'Report processing queued.'})
