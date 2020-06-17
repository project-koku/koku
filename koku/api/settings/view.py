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

from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common.permissions.settings_access import SettingsAccessPermission
from api.settings.ocp import OpenShiftSettings

LOG = logging.getLogger(__name__)
SETTINGS_GENERATORS = {"OCP": OpenShiftSettings}


class SettingsView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request):
        """
        Return a list of all settings.
        """
        settings = self._build_settings(request)
        return Response(settings)

    def post(self, request):
        """Handle all changed settings."""
        if not isinstance(request.data, dict):
            msg = "Invalid input format."
            raise ValidationError({"details": _(msg)})
        for settings_clazz in SETTINGS_GENERATORS.values():
            instance = settings_clazz(request)
            instance.handle_settings(request.data)
        return Response()

    def _build_settings(self, request):
        settings = []
        for settings_clazz in SETTINGS_GENERATORS.values():
            instance = settings_clazz(request)
            settings += instance.build_settings()

        return settings
