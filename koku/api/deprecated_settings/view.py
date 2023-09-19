#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
from datetime import datetime

from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common.permissions.settings_access import SettingsAccessPermission
from api.deprecated_settings.settings import Settings

SETTINGS_GENERATORS = {"settings": Settings}


class SettingsView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [SettingsAccessPermission]
    deprecation_datetime = datetime(2023, 9, 22)
    sunset_datetime = datetime(2023, 1, 10)
    link = "https://github.com/project-koku/koku/pull/4670"

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
