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

"""View for server status."""

import logging
import os
import platform
import subprocess
import sys

from flask import jsonify

from masu.api import API_VERSION
from masu.util.blueprint import application_route

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

API_V1_ROUTES = {}


@application_route('/status/', API_V1_ROUTES, methods=('GET',))
def get_status():
    """Packages response for class-based view."""
    status = ApplicationStatus()
    response = {
        'commit': status.commit,
        'python_version': status.python_version,
        'platform_info': status.platform_info,
        'modules': status.modules,
        'api_version': status.api_version
    }
    return jsonify(response)


# pylint: disable=too-few-public-methods
class ApplicationStatus():
    """A view that returns status JSON."""

    def _get_commit(self):  # pylint: disable=no-self-use
        """
        Collect the build number for the server.

        :returns: A build number

        """
        commit_info = os.environ.get('OPENSHIFT_BUILD_COMMIT', None)
        if commit_info is None:
            commit_info = subprocess.run(['git',
                                          'describe',
                                          '--always'],
                                         stdout=subprocess.PIPE)
            if commit_info.stdout:
                commit_info = commit_info.stdout.decode('utf-8').strip()
        return commit_info

    def _get_platform_info(self):  # pylint: disable=no-self-use
        """Collect the platform information.

        :returns: A dictionary of platform data
        """
        return platform.uname()._asdict()

    def _get_python_version(self):  # pylint: disable=no-self-use
        """Collect the python version information.

        :returns: The python version string.
        """
        return sys.version.replace('\n', '')

    def _get_modules(self):  # pylint: disable=no-self-use
        """Collect the installed modules.

        :returns: A dictonary of module names and versions.
        """
        module_data = {}
        for name, module in sorted(sys.modules.items()):
            if hasattr(module, '__version__'):
                module_data[str(name)] = str(module.__version__)
        return module_data

    commit = property(_get_commit)
    platform_info = property(_get_platform_info)
    python_version = property(_get_python_version)
    modules = property(_get_modules)
    api_version = API_VERSION

    def startup(self):
        """Log startup information."""
        logger.info('Platform:')
        for name, value in self.platform_info.items():
            logger.info('%s - %s ', name, value)

        logger.info('Python: %s', self.python_version)
        module_list = []
        for mod, version in self.modules.items():
            module_list.append('{mod} - {ver}'.format(mod=mod, ver=version))

        if module_list:
            logger.info('Modules: %s', ', '.join(module_list))
        else:
            logger.info('Modules: None')
        logger.info('Commit: %s', self.commit)
        logger.info('API Version: %s', self.api_version)
