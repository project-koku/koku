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
import socket
import subprocess
import sys

from flask import jsonify, request

from masu.api import API_VERSION
from masu.celery import celery as celery_app
from masu.config import Config
from masu.external.date_accessor import DateAccessor
from masu.util.blueprint import application_route

LOG = logging.getLogger(__name__)

API_V1_ROUTES = {}


@application_route('/status/', API_V1_ROUTES, methods=('GET',))
def get_status():
    """Packages response for class-based view."""
    if 'liveness' in request.args:
        return jsonify({'alive': True})

    app_status = ApplicationStatus()
    response = {
        'celery_status': app_status.celery_status,
        'commit': app_status.commit,
        'python_version': app_status.python_version,
        'platform_info': app_status.platform_info,
        'modules': app_status.modules,
        'api_version': app_status.api_version,
        'current_datetime': app_status.current_datetime,
        'debug': app_status.debug
    }
    return jsonify(response)


# pylint: disable=too-few-public-methods, no-self-use
class ApplicationStatus():
    """A view that returns status JSON."""

    api_version = API_VERSION

    def __init__(self):
        """Initialize an ApplicationStatus object."""
        self._events = dict()

    def _announce_worker_event(self, event):
        """Announce worker events."""
        state = celery_app.events.State()
        state.event(event)
        LOG.debug(f'EVENT: {event}')
        self._events[event.pop('hostname')] = event

    @property
    def celery_status(self):
        """Determine the status of our connection to Celery.

        :returns: dict of celery status
        """
        with celery_app.connection() as connection:
            recv = celery_app.events.Receiver(connection, handlers={
                'worker-offline': self._announce_worker_event,
                'worker-online': self._announce_worker_event,
                'worker-heartbeat': self._announce_worker_event,
            })
            try:
                recv.capture(limit=5, timeout=5, wakeup=True)
            except socket.timeout:
                LOG.warning('Timeout connecting to message broker.')
                return {'ERROR': 'connection timeout'}
            except ConnectionResetError:
                LOG.warning('Connection reset by message broker.')
                return {'ERROR': 'connection reset'}

            if len(self._events) > 5:
                # Receiver will run indefinitely unless we tell it to stop.
                recv.should_stop = True

        return self._events

    @property
    def commit(self):
        """
        Collect the build number for the server.

        :returns: A build number

        """
        commit_info = os.environ.get('OPENSHIFT_BUILD_COMMIT', None)
        if not commit_info:
            commit_info = subprocess.run(['git',
                                          'describe',
                                          '--always'],
                                         stdout=subprocess.PIPE)
            if commit_info.stdout:
                commit_info = commit_info.stdout.decode('utf-8').strip()
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
        return sys.version.replace('\n', '')

    @property
    def modules(self):
        """Collect the installed modules.

        :returns: A dictonary of module names and versions.
        """
        module_data = {}
        for name, module in sorted(sys.modules.items()):
            if hasattr(module, '__version__'):
                module_data[str(name)] = str(module.__version__)
        return module_data

    @property
    def current_datetime(self):
        """Collect the service current datetime.

        :returns: The datetime string.
        """
        return DateAccessor().today()

    @property
    def debug(self):
        """Collect the debug state of the service.

        :returns: Boolean indicating debug status.
        """
        return Config.DEBUG

    def startup(self):
        """Log startup information."""
        LOG.info(f'API Version: {self.api_version}')
        LOG.info(f'Celery Status: {self.celery_status}')
        LOG.info(f'Commit: {self.commit}')
        LOG.info(f'Current Date: {self.current_datetime}')
        LOG.info(f'DEBUG enabled: {str(self.debug)}')

        LOG.info('Platform:')
        for name, value in self.platform_info.items():
            LOG.info(f'{name} - {value}')

        LOG.info('Python: %s', self.python_version)
        module_list = []
        for mod, version in self.modules.items():
            module_list.append(f'{mod} - {version}')

        if module_list:
            LOG.info('Modules: %s', ', '.join(module_list))
        else:
            LOG.info('Modules: None')
