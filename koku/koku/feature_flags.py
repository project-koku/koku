#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Create Unleash Client."""
import logging

from django.conf import settings
from UnleashClient import UnleashClient
from UnleashClient.strategies import Strategy

from .env import ENVIRONMENT


LOG = logging.getLogger(__name__)


log_level = getattr(logging, "WARNING")
if isinstance(getattr(logging, settings.UNLEASH_LOGGING_LEVEL), int):
    log_level = getattr(logging, settings.UNLEASH_LOGGING_LEVEL)
else:
    LOG.info(f"invalid UNLEASH_LOG_LEVEL: {settings.UNLEASH_LOGGING_LEVEL}. using default: `WARNING`")


def fallback_true(feature_name: str, context: dict) -> bool:
    return True


class KokuUnleashClient(UnleashClient):
    """Koku Unleash Client."""

    def destroy(self):
        """Override destroy so that cache is not deleted."""
        self.fl_job.remove()
        if self.metric_job:
            self.metric_job.remove()
        self.scheduler.shutdown()


class SchemaStrategy(Strategy):
    def load_provisioning(self) -> list:
        return self.parameters["schema-name"]

    def apply(self, context):
        default_value = False
        if "schema" in context and context["schema"] is not None:
            default_value = context["schema"] in self.parsed_provisioning
        return default_value


strategies = {
    # All new strategies should be added here.
    "schema-strategy": SchemaStrategy
}
headers = {}
if settings.UNLEASH_TOKEN:
    headers["Authorization"] = f"Bearer {settings.UNLEASH_TOKEN}"

UNLEASH_CLIENT = KokuUnleashClient(
    settings.UNLEASH_URL,
    "Cost Management",
    environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
    instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
    custom_headers=headers,
    custom_strategies=strategies,
    cache_directory=settings.UNLEASH_CACHE_DIR,
    verbose_log_level=log_level,
)
