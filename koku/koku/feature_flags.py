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
    """Mock Unleash Client that doesn't connect to Unleash server."""

    def __init__(self, *args, **kwargs):
        """Initialize mock client without connecting."""
        LOG.info("Using MockUnleashClient - Unleash is disabled")
        self.unleash_url = kwargs.get("url", "")
        self.unleash_app_name = kwargs.get("app_name", "")
        self.unleash_instance_id = kwargs.get("instance_id", "")
        self.metrics_headers = kwargs.get("custom_headers", {})
        self.unleash_custom_options = {}
        self.cache = None
        self.engine = None
        self.unleash_request_timeout = 30
        self.unleash_request_retries = 3
        self.unleash_project_name = None
        self.unleash_event_callback = None
        self._ready_callback = None

    def initialize_client(self):
        """No-op initialization."""
        LOG.debug("MockUnleashClient.initialize_client() - no-op")
        pass

    def is_enabled(self, feature_name: str, context: dict = None, fallback_function=None):
        """Return fallback value for feature flags."""
        LOG.debug(f"MockUnleashClient.is_enabled({feature_name}) - using fallback")
        if fallback_function:
            return fallback_function(feature_name, context or {})
        return False

    def destroy(self):
        """No-op destroy."""
        LOG.debug("MockUnleashClient.destroy() - no-op")
        pass


class KokuUnleashClient:
    """Koku Unleash Client."""

    def __init__(self, *args, **kwargs):
        """Initialize real Unleash client."""
        from UnleashClient import UnleashClient
        from UnleashClient.periodic_tasks import aggregate_and_send_metrics

        LOG.info("Using real KokuUnleashClient - Unleash is enabled")
        # Store the aggregate function for later use
        self._aggregate_and_send_metrics = aggregate_and_send_metrics

        # Create the real UnleashClient
        self._client = UnleashClient(*args, **kwargs)

    def __getattr__(self, name):
        """Delegate all other attributes to the real client."""
        return getattr(self._client, name)

    def initialize_client(self):
        """Initialize the real client."""
        return self._client.initialize_client()

    def is_enabled(self, feature_name: str, context: dict = None, fallback_function=None):
        """Check if feature is enabled."""
        return self._client.is_enabled(feature_name, context, fallback_function)

    def destroy(self):
        """Override destroy so that cache is not deleted."""
        self._client.fl_job.remove()
        if self._client.metric_job:
            self._client.metric_job.remove()

            # Flush metrics before shutting down.
            self._aggregate_and_send_metrics(
                url=self._client.unleash_url,
                app_name=self._client.unleash_app_name,
                connection_id=self._client.connection_id,
                instance_id=self._client.unleash_instance_id,
                headers=self._client.metrics_headers,
                custom_options=self._client.unleash_custom_options,
                request_timeout=self._client.unleash_request_timeout,
                engine=self._client.engine,
            )

        self._client.unleash_scheduler.shutdown()


# Create the appropriate client based on settings
if settings.ONPREM:
    LOG.info("Unleash is disabled via ONPREM setting")
    UNLEASH_CLIENT = MockUnleashClient(
        url=settings.UNLEASH_URL,
        app_name="Cost Management",
        environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
        instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
        custom_headers={},
        cache_directory=settings.UNLEASH_CACHE_DIR,
        verbose_log_level=log_level,
    )
else:
    LOG.info("Unleash is enabled - connecting to Unleash server")
    headers = {}
    if settings.UNLEASH_TOKEN:
        headers["Authorization"] = settings.UNLEASH_TOKEN

    UNLEASH_CLIENT = KokuUnleashClient(
        url=settings.UNLEASH_URL,
        app_name="Cost Management",
        environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
        instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
        custom_headers=headers,
        cache_directory=settings.UNLEASH_CACHE_DIR,
        verbose_log_level=log_level,
    )
