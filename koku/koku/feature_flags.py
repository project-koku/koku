#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Create Unleash Client."""
import logging

from django.conf import settings
from UnleashClient import UnleashClient
from UnleashClient.periodic_tasks import aggregate_and_send_metrics

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


class KokuUnleashClient(UnleashClient):
    """Koku Unleash Client."""

    def destroy(self):
        """Override destroy so that cache is not deleted."""
        self.fl_job.remove()
        if self.metric_job:
            self.metric_job.remove()

            # Flush metrics before shutting down.
            aggregate_and_send_metrics(
                url=self.unleash_url,
                app_name=self.unleash_app_name,
                connection_id=self.connection_id,
                instance_id=self.unleash_instance_id,
                headers=self.metrics_headers,
                custom_options=self.unleash_custom_options,
                request_timeout=self.unleash_request_timeout,
                engine=self.engine,
            )

        self.unleash_scheduler.shutdown()


class DisabledUnleashClient:
    """Mock Unleash client for on-prem deployments without Unleash server.

    Makes zero network calls and uses fallback functions for feature flags.
    This enables Koku to run in environments where Unleash is not available.
    """

    def __init__(self):
        """Initialize disabled client with no-op instance ID."""
        self.unleash_instance_id = "disabled-unleash-client"

    def is_enabled(self, feature_name, context=None, fallback_function=None):
        """Check if feature is enabled using fallback function only.

        Args:
            feature_name (str): Name of the feature flag
            context (dict): Context dict (ignored in disabled mode)
            fallback_function (callable): Function to determine feature state

        Returns:
            bool: Result of fallback_function or False if no fallback provided
        """
        if fallback_function:
            return fallback_function(feature_name, context or {})
        return False  # Safe default: feature disabled

    def initialize_client(self):
        """No-op: no client to initialize."""
        pass

    def destroy(self):
        """No-op: no resources to clean up."""
        pass


headers = {}
if settings.UNLEASH_TOKEN:
    headers["Authorization"] = settings.UNLEASH_TOKEN

if not settings.ONPREM:
    # SaaS: Use real Unleash client with server connection
    UNLEASH_CLIENT = KokuUnleashClient(
        url=settings.UNLEASH_URL,
        app_name="Cost Management",
        environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
        instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
        custom_headers=headers,
        cache_directory=settings.UNLEASH_CACHE_DIR,
        verbose_log_level=log_level,
    )
    LOG.info(f"Unleash client enabled (SaaS mode): {settings.UNLEASH_URL}")
else:
    # On-prem: Use mock client (no network calls)
    UNLEASH_CLIENT = DisabledUnleashClient()
    LOG.info("Unleash client disabled (on-prem mode) - using fallback functions only")
