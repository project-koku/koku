#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common SUBS functions and vars."""
import logging

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.util.common import convert_account


LOG = logging.getLogger(__name__)

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def enable_subs_processing(schema_name: str) -> bool:
    """Helper to determine if source is enabled for SUBS processing."""

    schema_name = convert_account(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(log_json(msg="enable_subs_processing context", context=context))

    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-processing", context)
        or settings.ENABLE_SUBS_PROCESSING_DEBUG
    )


def get_start_and_end_from_manifest_id(manifest_id):
    """Helper to get the start and end dates for the report."""

    start_date = None
    end_date = None

    with ReportManifestDBAccessor() as manifest_accessor:
        manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        if not manifest:
            return

        bill_date = manifest.billing_period_start_datetime.date()
        if bill_date:
            provider_uuid = manifest.provider_id
            manifest_list = manifest_accessor.get_manifest_list_for_provider_and_bill_date(provider_uuid, bill_date)
            if len(manifest_list) == 1:
                start_date = bill_date
                end_date = DateHelper().month_end(bill_date)

    return start_date, end_date
