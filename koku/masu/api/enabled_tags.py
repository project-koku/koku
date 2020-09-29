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
"""View for enable_tags masu admin endpoint."""
import logging

from django.views.decorators.cache import never_cache
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from reporting.models import OCPEnabledTagKeys


LOG = logging.getLogger(__name__)
RESPONSE_KEY = "tag_keys"


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def enabled_tags(request):
    """Set enabled OCP tags in the DB for testing."""
    if request.method == "GET":
        params = request.query_params
        schema_name = params.get("schema")

        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        with schema_context(schema_name):
            enabled_tags = OCPEnabledTagKeys.objects.all()
            tag_keys = [tag.key for tag in enabled_tags]

        msg = f"Retreived enabled tags {tag_keys} for schema: {schema_name}."
        LOG.info(msg)

        return Response({RESPONSE_KEY: tag_keys})

    if request.method == "POST":
        data = request.data

        schema_name = data.get("schema")
        if schema_name is None:
            errmsg = "schema is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        action = data.get("action")
        if action is None:
            errmsg = "action is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        tag_keys = data.get("tag_keys")

        with schema_context(schema_name):
            if action.lower() == "create":
                for key in tag_keys:
                    OCPEnabledTagKeys.objects.get_or_create(key=key)
                msg = f"Inserted enabled tags for schema: {schema_name}."
                LOG.info(msg)
            if action.lower() == "delete":
                for key in tag_keys:
                    OCPEnabledTagKeys.objects.filter(key=key).delete()
                msg = f"Deleted enabled tags for schema: {schema_name}."
                LOG.info(msg)

        return Response({RESPONSE_KEY: tag_keys})
