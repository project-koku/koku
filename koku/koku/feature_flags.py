#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Create Unleash Client."""
import logging
from unittest.mock import Mock

import requests
from django.conf import settings
from UnleashClient import UnleashClient
from UnleashClient.strategies import Strategy

from .env import ENVIRONMENT


log_level = getattr(logging, "WARNING")
if isinstance(getattr(logging, settings.UNLEASH_LOGGING_LEVEL), int):
    log_level = getattr(logging, settings.UNLEASH_LOGGING_LEVEL)
else:
    print(f"invalid UNLEASH_LOG_LEVEL: {settings.UNLEASH_LOGGING_LEVEL}. using default: `WARNING`")


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

UNLEASH_CLIENT = UnleashClient(
    settings.UNLEASH_URL,
    "Cost Management",
    environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
    instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
    custom_headers=headers,
    custom_strategies=strategies,
    cache_directory=settings.UNLEASH_CACHE_DIR,
    verbose_log_level=log_level,
)

if not UNLEASH_CLIENT.is_initialized:
    try:
        print(f"Initializing Unleash Client. URL: {settings.UNLEASH_URL}")
        requests.get(settings.UNLEASH_URL)
        UNLEASH_CLIENT.initialize_client()
    except requests.exceptions.ConnectionError:
        print("Unleash Server is not reachable. Using Mock client.")
        UNLEASH_CLIENT = Mock()
        UNLEASH_CLIENT.is_enabled.return_value = False
