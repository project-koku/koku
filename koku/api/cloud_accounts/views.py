#
# Copyright 2019 Red Hat, Inc.
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
"""View for Cloud Account."""
import json
import logging
import os

from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings
from api.cloud_accounts.serializers import CloudAccountSerializer
from koku.settings import BASE_DIR

LOG = logging.getLogger(__name__)
CLOUD_ACCOUNTS_FILE_NAME = os.path.join(BASE_DIR, "api/cloud_accounts/data/cloud_accounts.json")
"""View for Cloud Accounts."""


class CloudAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """View for Cloud Accounts."""

    serializer_class = CloudAccountSerializer
    permission_classes = (AllowAny,)
    renderer_classes = [JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES

    def get_queryset(self):
        """ViewSet get_queryset method."""
        data = self.get_json(CLOUD_ACCOUNTS_FILE_NAME)
        return data

    def get_json(self, path):
        """Obtain API JSON data from file path."""
        json_data = None
        with open(path) as json_file:
            try:
                json_data = json.load(json_file)
            except (IOError, json.JSONDecodeError) as exc:
                LOG.exception(exc)
        return json_data
