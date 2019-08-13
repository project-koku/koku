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

"""Test the status endpoint view."""

import logging
import os
import re
from collections import namedtuple
from datetime import datetime
from subprocess import CompletedProcess, PIPE
from unittest.mock import ANY, Mock, PropertyMock, patch

from django.db import InterfaceError
from django.test import TestCase
from django.test.utils import override_settings


from masu.api import API_VERSION
from masu.api.status import (
    ApplicationStatus,
    BROKER_CONNECTION_ERROR,
    CELERY_WORKER_NOT_FOUND,
    get_status,
)
from masu.test import MasuTestCase

@override_settings(ROOT_URLCONF='masu.urls')
class StatusAPITest(TestCase):
    """Test Cases for the Status API."""

    def setUp(self):
        super().setUp()
        logging.disable(logging.NOTSET)

    def test_status(self):
        """Test the status endpoint."""
        response = self.client.get('/api/v1/status/')
        body = response.data

        self.assertEqual(response.status_code, 200)
        #self.assertEqual(response.headers['Content-Type'], 'application/json')

        self.assertIn('api_version', body)
        self.assertIn('celery_status', body)
        self.assertIn('commit', body)
        self.assertIn('current_datetime', body)
        self.assertIn('database_status', body)
        self.assertIn('debug', body)
        self.assertIn('modules', body)
        self.assertIn('platform_info', body)
        self.assertIn('python_version', body)

        self.assertEqual(body['api_version'], API_VERSION)
        self.assertIsNotNone(body['celery_status'])
        self.assertIsNotNone(body['commit'])
        self.assertIsNotNone(body['current_datetime'])
        self.assertIsNotNone(body['database_status'])
        self.assertIsNotNone(body['debug'])
        self.assertIsNotNone(body['modules'])
        self.assertIsNotNone(body['platform_info'])
        self.assertIsNotNone(body['python_version'])

    @patch.dict(os.environ, {'OPENSHIFT_BUILD_COMMIT': 'fake_commit_hash'})
    def test_commit_with_env(self):
        """Test the commit method via environment."""
        result = ApplicationStatus().commit
        self.assertEqual(result, 'fake_commit_hash')

    @patch('masu.api.status.subprocess.run')
    @patch('masu.api.status.os.environ.get', return_value=dict())
    def test_commit_with_subprocess(self, mock_os, mock_subprocess):
        """Test the commit method via subprocess."""
        expected = 'buildnum'

        args = {
            'args': ['git', 'describe', '--always'],
            'returncode': 0,
            'stdout': bytes(expected, encoding='UTF-8'),
        }
        mock_subprocess.return_value = Mock(spec=CompletedProcess, **args)

        result = ApplicationStatus().commit

        mock_os.assert_called_with('OPENSHIFT_BUILD_COMMIT', None)
        mock_subprocess.assert_called_with(args['args'], stdout=PIPE)
        self.assertEqual(result, expected)

    @patch('masu.api.status.subprocess.run')
    @patch('masu.api.status.os.environ.get', return_value=dict())
    def test_commit_with_subprocess_nostdout(self, mock_os, mock_subprocess):
        """Test the commit method via subprocess when stdout is none."""

        args = {
            'args': ['git', 'describe', '--always'],
            'returncode': 0,
            'stdout': None,
        }
        mock_subprocess.return_value = Mock(spec=CompletedProcess, **args)

        result = ApplicationStatus().commit

        mock_os.assert_called_with('OPENSHIFT_BUILD_COMMIT', None)
        mock_subprocess.assert_called_with(args['args'], stdout=PIPE)
        self.assertIsNone(result.stdout)

    @patch('masu.api.status.platform.uname')
    def test_platform_info(self, mock_platform):
        """Test the platform_info method."""
        platform_record = namedtuple('Platform', ['os', 'version'])
        a_plat = platform_record('Red Hat', '7.4')
        mock_platform.return_value = a_plat
        result = ApplicationStatus().platform_info
        self.assertEqual(result['os'], 'Red Hat')
        self.assertEqual(result['version'], '7.4')

    @patch('masu.api.status.sys.version')
    def test_python_version(self, mock_sys_ver):
        """Test the python_version method."""
        expected = 'Python 3.6'
        mock_sys_ver.replace.return_value = expected
        result = ApplicationStatus().python_version
        self.assertEqual(result, expected)

    @patch('masu.api.status.sys.modules')
    def test_modules(self, mock_modules):
        """Test the modules method."""
        expected = {'module1': 'version1', 'module2': 'version2'}
        mod1 = Mock(__version__='version1')
        mod2 = Mock(__version__='version2')
        mock_modules.items.return_value = (('module1', mod1), ('module2', mod2))
        result = ApplicationStatus().modules
        self.assertEqual(result, expected)

    @patch('masu.api.status.LOG.info')
    def test_startup_with_modules(self, mock_logger):
        """Test the startup method with a module list."""
        ApplicationStatus().startup()
        mock_logger.assert_called_with(ANY, ANY)

    @patch('masu.api.status.ApplicationStatus.modules', new_callable=PropertyMock)
    def test_startup_without_modules(self, mock_mods):
        """Test the startup method without a module list."""
        mock_mods.return_value = {}
        expected = 'INFO:masu.api.status:Modules: None'

        with self.assertLogs('masu.api.status', level='INFO') as logger:
            ApplicationStatus().startup()
            self.assertIn(expected, logger.output)

    @patch('masu.external.date_accessor.DateAccessor.today')
    def test_get_datetime(self, mock_date):
        """Test the startup method for datetime."""
        mock_date_string = '2018-07-25 10:41:59.993536'
        mock_date_obj = datetime.strptime(mock_date_string, '%Y-%m-%d %H:%M:%S.%f')
        mock_date.return_value = mock_date_obj
        expected = 'INFO:masu.api.status:Current Date: {}'.format(
            mock_date.return_value
        )
        with self.assertLogs('masu.api.status', level='INFO') as logger:
            ApplicationStatus().startup()
            self.assertIn(str(expected), logger.output)

    def test_get_debug(self):
        """Test the startup method for debug state."""
        expected = 'INFO:masu.api.status:DEBUG enabled: {}'.format(str(False))
        with self.assertLogs('masu.api.status', level='INFO') as logger:
            ApplicationStatus().startup()
            self.assertIn(str(expected), logger.output)

    @patch('masu.api.status.celery_app')
    def test_startup_has_celery_status(self, mock_celery):
        """test celery status is in startup() output."""
        expected_status = {'Status': 'OK'}
        expected = f'INFO:masu.api.status:Celery Status: {expected_status}'

        mock_control = mock_celery.control
        mock_control.inspect.return_value.stats.return_value = expected_status

        with self.assertLogs('masu.api.status', level='INFO') as logger:
            ApplicationStatus().startup()
            self.assertIn(expected, logger.output)

    @patch('masu.api.status.celery_app')
    def test_celery_status(self, mock_celery):
        """Test that an error status is returned when Celery is down."""
        expected_status = {'Status': 'OK'}
        mock_control = mock_celery.control
        mock_control.inspect.return_value.stats.return_value = expected_status

        status = ApplicationStatus().celery_status
        self.assertEqual(status, expected_status)

    @patch('masu.api.status.celery_app')
    def test_celery_status_no_stats(self, mock_celery):
        """Test that an error status is returned when Celery is down."""
        mock_control = mock_celery.control
        mock_control.inspect.return_value.stats.return_value = None

        expected_status = {'Error': CELERY_WORKER_NOT_FOUND}
        status = ApplicationStatus().celery_status
        self.assertEqual(status, expected_status)

    @patch('masu.api.status.celery_app')
    def test_celery_heartbeat_failure(self, mock_celery):
        """Test that heartbeat failure logs connection to broker issue."""
        mock_conn = mock_celery.connection.return_value
        mock_conn.heartbeat_check.side_effect = ConnectionRefusedError

        expected_status = {'Error': BROKER_CONNECTION_ERROR}
        status = ApplicationStatus().celery_status
        self.assertEqual(status, expected_status)

    @patch('masu.api.status.celery_app')
    def test_celery_status_connection_reset(self, mock_celery):
        """Test that the status retrys on connection reset."""
        mock_celery.control.inspect.side_effect = ConnectionResetError
        stat = ApplicationStatus()
        result = stat._check_celery_status()

        self.assertIn('Error', result)

        result = stat.celery_status

        self.assertIn('Error', result)
        # celery_app.control.inspect

    def test_database_status(self):
        """test that fetching database status works."""
        expected = re.compile(r'INFO:masu.api.status:Database: \[{.*postgres.*}\]')
        with self.assertLogs('masu.api.status', level='INFO') as logger:
            ApplicationStatus().startup()
            results = None
            for line in logger.output:
                if not results:
                    results = expected.search(line)
            self.assertIsNotNone(results)

    def test_database_status_fail(self):
        """test that fetching database handles errors."""
        expected = 'WARNING:masu.api.status:Unable to connect to DB: '
        with patch('django.db.backends.utils.CursorWrapper') as mock_cursor:
            mock_cursor = mock_cursor.return_value.__enter__.return_value
            mock_cursor.execute.side_effect = InterfaceError()
            with self.assertLogs('masu.api.status', level='INFO') as logger:
                ApplicationStatus().startup()
                self.assertIn(expected, logger.output)

    def disablefornowtest_liveness(self):
        """Test the liveness response."""
        expected = {'alive': True}
        app = create_app(test_config=dict())

        with app.test_request_context('/?liveness'):
            response = get_status()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, expected)
