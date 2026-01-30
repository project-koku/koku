#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for server status."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from api.status.models import Status
from api.status.serializers import StatusSerializer


class StatusView(APIView):
    """Provide the server status information."""

    permission_classes = [permissions.AllowAny]
    serializer_class = StatusSerializer

    @method_decorator(never_cache)
    def get(self, request):
        """Return the server status."""
        status_info = Status()
        serializer = StatusSerializer(status_info)
        server_info = serializer.data
        return Response(server_info)
