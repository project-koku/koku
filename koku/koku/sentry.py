"""Sentry configuration file for the Koku project."""
import logging

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .env import ENVIRONMENT

LOG = logging.getLogger(__name__)

if ENVIRONMENT.bool("KOKU_API_ENABLE_SENTRY", default=False):
    LOG.info("Enabling sentry for koku api.")
    sentry_sdk.init(
        dsn=ENVIRONMENT("KOKU_SENTRY_DSN"),
        environment=ENVIRONMENT("KOKU_SENTRY_ENVIRONMENT"),
        integrations=[DjangoIntegration()],
    )
    LOG.info("Sentry setup.")
elif ENVIRONMENT.bool("KOKU_CELERY_ENABLE_SENTRY", default=False):
    LOG.info("Enabling sentry for celery worker.")
    sentry_sdk.init(
        dsn=ENVIRONMENT("KOKU_CELERY_SENTRY_DSN"),
        environment=ENVIRONMENT("KOKU_SENTRY_ENVIRONMENT"),
        integrations=[CeleryIntegration()],
    )
    LOG.info("Sentry setup.")
else:
    LOG.info("Sentry not enabled.")
