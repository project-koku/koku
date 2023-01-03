"""Sentry configuration file for the Koku project."""
import logging

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .env import ENVIRONMENT

LOG = logging.getLogger(__name__)

BLOCK_LIST = [
    "/api/cost-management/v1/status/",
    "/api/cost-management/v1/source-status/",
]


def traces_sampler(sampling_context):
    if sampling_context["transaction_context"]["op"] == "http.server" and any(
        blocked in sampling_context["transaction_context"]["name"] for blocked in BLOCK_LIST
    ):
        # Drop this transaction, by setting its sample rate to 0%
        return 0

    # Default sample rate for all others (replaces traces_sample_rate)
    return 0.25


if ENVIRONMENT.bool("KOKU_API_ENABLE_SENTRY", default=False):
    LOG.info("Enabling sentry for koku api.")
    sentry_sdk.init(
        dsn=ENVIRONMENT("KOKU_SENTRY_DSN"),
        environment=ENVIRONMENT("KOKU_SENTRY_ENVIRONMENT"),
        integrations=[DjangoIntegration()],
        traces_sampler=traces_sampler,
    )
    LOG.info("Sentry setup.")
elif ENVIRONMENT.bool("KOKU_CELERY_ENABLE_SENTRY", default=False):
    LOG.info("Enabling sentry for celery worker.")
    sentry_sdk.init(
        dsn=ENVIRONMENT("KOKU_CELERY_SENTRY_DSN"),
        environment=ENVIRONMENT("KOKU_SENTRY_ENVIRONMENT"),
        integrations=[CeleryIntegration()],
        traces_sampler=traces_sampler,
    )
    LOG.info("Sentry setup.")
else:
    LOG.info("Sentry not enabled.")
