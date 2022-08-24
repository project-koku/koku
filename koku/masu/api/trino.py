#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for trino query endpoint."""
# flake8: noqa
import logging

import trino
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework_csv.renderers import CSVRenderer

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES) + (CSVRenderer,))
def trino_query(request):
    """Run a trino query."""
    if request.method == "POST":
        data = request.data
        query = data.get("query")
        schema_name = data.get("schema")

        if query is None:
            errmsg = "Must provide a query key to run."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if schema_name is None:
            errmsg = "Must provide a schema key to run."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        lowered_query = query.lower()
        dissallowed_keywords = ["delete", "insert", "update", "alter", "create", "drop", "grant"]
        for keyword in dissallowed_keywords:
            if keyword in lowered_query:
                errmsg = f"This endpoint does not allow a {keyword} operation to be performed."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        msg = f"Running Trino query: {query}"
        LOG.info(msg)

        with trino.dbapi.connect(
            host=settings.PRESTO_HOST, port=settings.PRESTO_PORT, user="admin", catalog="hive", schema=schema_name
        ) as conn:
            cur = conn.cursor()
            cur.execute(query)
            cols = [des[0] for des in cur.description]
            rows = cur.fetchall()
            results = []
            for row in rows:
                result = {}
                for i, value in enumerate(row):
                    result[cols[i]] = value
                results.append(result)

        return Response(results)
