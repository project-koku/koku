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
import uuid

from django.db import models

from api import API_VERSION

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Status(models.Model):
    """A server's status."""

    server_id = models.UUIDField(default=uuid.uuid4,
                                 editable=False)

    def get_commit(self):  # pylint: disable=R0201
        """Collect the build number for the server.

        :returns: A build number
        """
        commit_info = os.environ.get('KOKU_COMMIT', None)
        if commit_info is None:
            commit_info = subprocess.run(['git',
                                          'describe',
                                          '--always'],
                                         stdout=subprocess.PIPE)
            if commit_info.stdout:
                commit_info = commit_info.stdout.decode('utf-8').strip()
        return commit_info

    def get_platform_info(self):  # pylint: disable=R0201
        """Collect the platform information.

        :returns: A dictionary of platform data
        """
        return platform.uname()._asdict()


    def get_python_version(self):  # pylint: disable=R0201
        """Collect the python version information.

        :returns: The python version string.
        """
        return sys.version.replace('\n', '')


    def get_modules(self):  # pylint: disable=R0201
        """Collect the installed modules.

        :returns: A dictonary of module names and versions.
        """
        module_data = {}
        for name, module in sorted(sys.modules.items()):
            if hasattr(module, '__version__'):
                module_data[str(name)] = str(module.__version__)
        return module_data

    commit = property(get_commit)
    platform_info = property(get_platform_info)
    python_version = property(get_python_version)
    modules = property(get_modules)
    api_version = API_VERSION


    def startup(self):
        """Log startup information."""
        logger.info('Platform:')
        for name, value in self.platform_info.items():
            logger.info('%s - %s ', name, value)

        logger.info('Python: %s', self.python_version)
        module_list = []
        for name, value in self.modules.items():
            module_list.append(module_list.append(f'{name} - {value}'))
        if module_list:
            logger.info('Modules: None')
        else:
            logger.info('Modules: %s', ', '.join(module_list))
        logger.info('Commit: %s', self.commit)
        logger.info('Server Id: %s', self.server_id)
        logger.info('API Version: %s', self.api_version)
