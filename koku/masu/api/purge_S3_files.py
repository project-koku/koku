#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for removing parquet & csv files for a particular provider."""
import logging
from uuid import UUID

from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from koku.feature_flags import UNLEASH_CLIENT
from masu.celery.tasks import deleted_archived_with_prefix
from masu.database.provider_collector import ProviderCollector
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor


def enable_purge_turnpikes(account):  # pragma: no cover #noqa
    """Helper to determine if source is enabled for HCS."""
    if account and not account.startswith("acct"):
        account = f"acct{account}"

    context = {"schema": account}
    LOG.info(f"enable-purge-turnpikes context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("enable-purge-turnpike", context))


LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def purge_trino_files(request):
    """
    This endpoint deletes the parquet & csv files in s3.
    Required Params:
        provider_uuid - source_uuid
        schema - account schema
        bill_date - usually the start of the month example 08-12-2022
    Optional:
        simulate - returns the s3 paths that would be deleted.
    """
    # Parameter Validation
    params = request.query_params
    if not params:
        errmsg = "Parameter missing. Required: provider_uuid, schema, bill date"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    provider_uuid = params.get("provider_uuid")
    with ProviderCollector() as collector:
        all_providers = collector.get_provider_uuid_map()
        provider = all_providers.get(str(provider_uuid))
        if not provider:
            errmsg = f"The provider_uuid {provider_uuid} does not exist."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    provider_type = provider.type
    schema = params.get("schema")
    bill_date = params.get("bill_date")
    context = {"start_date": bill_date}
    # Use ParquetReportProcessor to build s3 paths
    pq_processor_object = ParquetReportProcessor(
        schema_name=schema,
        report_path=None,
        provider_uuid=provider_uuid,
        provider_type=provider_type,
        manifest=None,
        context=context,
    )
    path_info = {
        "s3_csv_path": pq_processor_object.csv_path_s3,
        "s3_parquet_path": pq_processor_object.parquet_path_s3,
        "s3_daily_parquet_path": pq_processor_object.parquet_daily_path_s3,
        "s3_daily_openshift_path": pq_processor_object.parquet_ocp_on_cloud_path_s3,
    }
    log_msg = f"""
        Purge Parameters:
            schema: {schema}
            bill_date: {bill_date}
            provider_type: {provider_type}
            provider_uuid: {provider_uuid}
        """
    LOG.info(log_msg)
    if params.get("stimulate"):
        return Response(path_info)

    # Checking to see if account is enabled in unleash
    unleash_check = enable_purge_turnpikes(schema)
    if not unleash_check:
        errmsg = f"Schema {schema} not enabled in unleash."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    for _, file_prefix in path_info.items():
        LOG.info(f"Starting to delete for path: {file_prefix}")
        deleted_archived_with_prefix(settings.S3_BUCKET_NAME, file_prefix)
