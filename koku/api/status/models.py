#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models to capture server status."""
import logging
import platform
import sys

from django.conf import settings

from api import API_VERSION
from koku.rbac import RbacService
from masu.config import Config

LOG = logging.getLogger(__name__)


class Status:
    """A server's status."""

    config = Config

    @property
    def commit(self):
        """Collect the build number for the server.

        :returns: A build number
        """
        return settings.GIT_COMMIT

    @property
    def platform_info(self):
        """Collect the platform information.

        :returns: A dictionary of platform data
        """
        return platform.uname()._asdict()

    @property
    def python_version(self):
        """Collect the python version information.

        :returns: The python version string.
        """
        return sys.version.replace("\n", "")

    @property
    def modules(self):
        """Collect the installed modules.

        :returns: A dictonary of module names and versions.
        """
        module_data = {}
        for name, module in sorted(sys.modules.items()):
            if hasattr(module, "__version__"):
                module_data[str(name)] = str(module.__version__)
        return module_data

    @property
    def api_version(self):
        """Return the API version."""
        return API_VERSION

    def startup(self):
        """Log startup information."""
        LOG.info("Platform:")
        for name, value in self.platform_info.items():
            LOG.info("%s - %s ", name, value)

        LOG.info("Python: %s", self.python_version)
        module_list = []
        for mod, version in self.modules.items():
            module_list.append(f"{mod} - {version}")

        if module_list:
            LOG.info("Modules: %s", ", ".join(module_list))
        else:
            LOG.info("Modules: None")
        LOG.info("Commit: %s", self.commit)
        LOG.info("API Version: %s", self.api_version)

    @property
    def rbac_cache_ttl(self):
        """Get the RBAC cache ttl."""
        return RbacService().get_cache_ttl()
