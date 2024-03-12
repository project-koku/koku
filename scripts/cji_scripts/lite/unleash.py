#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from UnleashClient import UnleashClient

from .env import ENVIRONMENT


class LiteUnleashClient(UnleashClient):
    """Lite Unleash Client."""

    def destroy(self):
        """Override destroy so that cache is not deleted."""
        self.fl_job.remove()
        if self.metric_job:
            self.metric_job.remove()
        self.scheduler.shutdown()


def new_unleash_client(settings):
    headers = {}
    if settings.UNLEASH_TOKEN:
        headers["Authorization"] = f"Bearer {settings.UNLEASH_TOKEN}"

    return LiteUnleashClient(
        url=settings.UNLEASH_URL,
        app_name="Cost Management",
        environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
        instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
        custom_headers=headers,
        cache_directory=settings.UNLEASH_CACHE_DIR,
        verbose_log_level=settings.LOGGING_LEVEL,
    )
