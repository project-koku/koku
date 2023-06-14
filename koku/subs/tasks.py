#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch"""
import logging

from api.provider.models import Provider
from koku import celery_app

LOG = logging.getLogger(__name__)

SUBS_QUEUE = "subs"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_QUEUE]

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def check_schema_name(schema_name: str) -> str:
    # Implement the logic for checking and modifying the schema name if needed
    pass


def enable_subs_processing(schema_name: str) -> bool:
    # Implement the logic to determine if the source is enabled for SUBS processing
    pass


@celery_app.task(name="subs.tasks.collect_subs_report_data_from_manifest", queue=SUBS_QUEUE)
def collect_subs_report_data_from_manifest(args):
    # Implement the functionality of the new task
    pass


@celery_app.task(name="subs.tasks.collect_subs_report_data", queue=SUBS_QUEUE)
def collect_subs_report_data(
    self, schema_name, provider_type, provider_uuid, start_date=None, end_date=None, tracing_id=None, finalize=False
):
    # Implement the functionality of the new task
    pass


def get_providers_for_subs():
    # Implement the logic to fetch and filter providers for SUBS processing
    pass
