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
