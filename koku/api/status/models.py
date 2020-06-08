#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Models to capture server status."""
import logging
import os
import platform
import subprocess
import sys

from api import API_VERSION
from koku.rbac import RbacService

logger = logging.getLogger(__name__)


class Status:
    """A server's status."""

    @property
    def commit(self):
        """Collect the build number for the server.

        :returns: A build number
        """
        commit_info = os.environ.get("OPENSHIFT_BUILD_COMMIT", None)
        if commit_info is None:
            commit_info = subprocess.run(["git", "describe", "--always"], stdout=subprocess.PIPE)
            if commit_info.stdout:
                commit_info = commit_info.stdout.decode("utf-8").strip()
        return commit_info

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
        logger.info("Platform:")
        for name, value in self.platform_info.items():
            logger.info("%s - %s ", name, value)

        logger.info("Python: %s", self.python_version)
        module_list = []
        for mod, version in self.modules.items():
            module_list.append(f"{mod} - {version}")

        if module_list:
            logger.info("Modules: %s", ", ".join(module_list))
        else:
            logger.info("Modules: None")
        logger.info("Commit: %s", self.commit)
        logger.info("API Version: %s", self.api_version)

    @property
    def rbac_cache_ttl(self):
        """Get the RBAC cache ttl."""
        return RbacService().get_cache_ttl()
