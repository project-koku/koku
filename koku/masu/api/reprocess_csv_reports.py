#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for expired_data endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.provider.models import Provider
from masu.processor.orchestrator import Orchestrator
from masu.util.common import DateHelper

LOG = logging.getLogger(__name__)


def check_required_parameters(query_params):
    """Validates the expected query parameters."""
    for param in ["start_date", "provider_uuid"]:
        if not query_params.get(param):
            return f"{param} must be supplied as a parameter."


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def reprocess_csv_reports(request):
    """trigger a task to reprocess monthly csv files into parquet files for a provider."""
    params = request.query_params
    errmsg = check_required_parameters(params)
    if errmsg:
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    provider_uuid = params.get("provider_uuid")
    summarize_reports = params.get("summarize_reports", "true").lower()
    summarize_reports = True if summarize_reports == "true" else False

    provider = Provider.objects.filter(uuid=provider_uuid).first()
    schema = provider.account.get("schema_name")
    report_month = DateHelper().month_start(params.get("start_date"))

    orchestrator = Orchestrator()

    # TODO
    # 1. Should we enable by provider type too (might need batching logic)
    # 2. The ability to trigger multiple months for a/each provider.
    # 3. Add safety measures to ensure you can't retrigger this back to back.

    manifest_list, reports_tasks_queued = orchestrator.start_manifest_processing(
        customer_name=schema,
        credentials={},
        data_source={},
        provider_type=provider.type,
        schema_name=schema,
        provider_uuid=provider_uuid,
        report_month=report_month,
        summarize_reports=summarize_reports,
        reprocess_csv_reports=True,
    )
    # Cody:
    # One potential problem with hooking into the already existing start_manifest_processing,
    # is that you would kick off another sub_task & hcs_task as well. I am curious to what
    # impact this might have on those tasks.
    return Response(
        {
            "Triggering provider reprocessing": {provider_uuid},
            "Billing month": {report_month},
            "Manifest ids": str(manifest_list),
            "Reports queued": str(reports_tasks_queued),
        }
    )
