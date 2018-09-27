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
"""Test the API apps module."""
import logging
from unittest.mock import patch

from django.apps import apps
from django.db.utils import OperationalError
from django.test import TestCase

from api.apps import ApiConfig as KokuApiConfig


class AppsModelTest(TestCase):
    """Tests against the apps functions."""

    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        # remove filters on logging
        logging.disable(logging.NOTSET)

    @classmethod
    def tearDownClass(cls):
        """Tear down test class."""
        # restore filters on logging
        logging.disable(logging.CRITICAL)

    @patch('api.apps.sys.argv', ['manage.py', 'test'])
    @patch('api.apps.ApiConfig.startup_status')
    def test_ready_silent_run(self, mock_status):
        """Test that ready functions are not called."""
        mock_status.assert_not_called()

    def test_startup_status(self):
        """Test the server status startup."""
        with self.assertLogs('api.status.models', level='INFO') as logger:
            api_config = apps.get_app_config('api')
            api_config.startup_status()
            self.assertNotEqual(logger.output, [])

    # patching a method called by ApiConfig.ready()
    @patch.object(KokuApiConfig, 'startup_status',
                  lambda x: exec('raise OperationalError("This is a Test Exception")'))
    def test_catch_operational_error(self):
        """Test that we handle exceptions thrown when tables are missing."""
        api_config = apps.get_app_config('api')

        # the real test
        api_config.ready()

        # sanity-checking that the mocked object is raising the expected error
        with self.assertRaises(OperationalError):
            api_config.startup_status()
