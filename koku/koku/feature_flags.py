#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Create Unleash Client."""
import logging

from django.conf import settings

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


class MockUnleashClient:
    """Mock Unleash Client for ONPREM mode."""

    def __init__(self, instance_id, **kwargs):
        """Initialize mock client with only instance_id."""
        LOG.info("Using MockUnleashClient - Unleash is disabled")
        self.unleash_instance_id = instance_id

    def initialize_client(self):
        """No-op initialization."""
        pass

    def is_enabled(self, feature_name: str, context: dict = None, fallback_function=None):
        """Return fallback value for feature flags."""
        if fallback_function:
            return fallback_function(feature_name, context or {})
        return False

    def destroy(self):
        """No-op destroy."""
        pass


# Create the appropriate client based on settings
if settings.ONPREM:
    LOG.info("Unleash is disabled via ONPREM setting")
    UNLEASH_CLIENT = MockUnleashClient(
        instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python")
    )
else:
    LOG.info("Unleash is enabled - connecting to Unleash server")
    from UnleashClient import UnleashClient

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
