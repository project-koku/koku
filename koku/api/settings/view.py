#
# Copyright 2020 Red Hat, Inc.
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
"""View for Settings."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from api.settings.ocp import OpenShiftSettings
from api.settings.utils import OPENSHIFT_SETTINGS_PREFIX

LOG = logging.getLogger(__name__)
SETTINGS_GENERATORS = {"OCP": OpenShiftSettings}


class SettingsView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [permissions.AllowAny]

    @never_cache
    def get(self, request):
        """
        Return a list of all settings.
        """
        tabs = self._build_tabs(request)
        settings = [{"fields": [tabs]}]
        return Response(settings)

    def post(self, request):
        """Handle all changed settings."""
        for settings_clazz in SETTINGS_GENERATORS.values():
            instance = settings_clazz(request)
            instance.handle_settings(request.data)
        return Response()

    def _build_tabs(self, request):
        tab_items = []
        for settings_clazz in SETTINGS_GENERATORS.values():
            instance = settings_clazz(request)
            tab_items += instance.build_tabs()

        tabs = {"name": f"{OPENSHIFT_SETTINGS_PREFIX}.tabs", "fields": tab_items, "component": "tabs"}
        return tabs
