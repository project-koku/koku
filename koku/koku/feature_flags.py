#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Create Unleash Client."""
import logging

from django.conf import settings
from UnleashClient import UnleashClient

from .env import ENVIRONMENT

LOG = logging.getLogger(__name__)

log_level = getattr(logging, "WARNING")
if isinstance(getattr(logging, settings.UNLEASH_LOGGING_LEVEL), int):
    log_level = getattr(logging, settings.UNLEASH_LOGGING_LEVEL)
else:
    LOG.info(f"invalid UNLEASH_LOG_LEVEL: {settings.UNLEASH_LOGGING_LEVEL}. using default: `WARNING`")


def fallback_true(feature_name: str, context: dict) -> bool:
    return True


def fallback_development_true(feature_name: str, context: dict) -> bool:
    return context.get("environment", "").lower() == "development"


headers = {}
if settings.UNLEASH_TOKEN:
    headers["Authorization"] = settings.UNLEASH_TOKEN

UNLEASH_CLIENT = UnleashClient(
    url=settings.UNLEASH_URL,
    app_name="Cost Management",
    environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
    instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
    custom_headers=headers,
    cache_directory=settings.UNLEASH_CACHE_DIR,
    verbose_log_level=log_level,
)
