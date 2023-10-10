#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.permissions.settings_access import SettingsAccessPermission
from api.deprecated_settings.settings import Settings
from api.settings.serializers import NonEmptyListSerializer
from reporting.provider.ocp.models import OpenshiftCostCategory

SETTINGS_GENERATORS = {"settings": Settings}


class PlatformCategoriesView(APIView):
    """View to manage platform categories

    Projects added will be considered part of the platform cost.
    Default projects may not be deleted.
    """

    permission_classes = (SettingsAccessPermission,)
    _default_platform_projects = ("kube-%", "openshift-%", "Platform unallocated")

    @property
    def _platform_record(self):
        return OpenshiftCostCategory.objects.get(name="Platform")

    def get(self, request):
        return Response(
            {
                "platform_namespaces": self._platform_record.namespace,
            }
        )

    def put(self, request):
        serializer = NonEmptyListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        projects = serializer.validated_data["projects"]
        platform_record = self._platform_record
        platform_record.namespace = list(set(platform_record.namespace).union(projects))
        platform_record.save()

        return Response(platform_record.namespace)

    def delete(self, request):
        serializer = NonEmptyListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        projects = serializer.validated_data["projects"]
        request_without_defaults = set(projects).difference(self._default_platform_projects)
        platform_record = self._platform_record
        platform_record.namespace = list(set(platform_record.namespace).difference(request_without_defaults))
        platform_record.save()

        # TODO: Formulate this response to be more in line with other responses
        return Response(
            {
                "platform_namespaces": self._platform_record.namespace,
            }
        )
