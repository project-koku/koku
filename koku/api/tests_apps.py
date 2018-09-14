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
from django.contrib.auth.models import User
from django.db.utils import OperationalError, ProgrammingError
from django.test import TestCase

from api.apps import ApiConfig as KokuApiConfig
from koku.env import ENVIRONMENT


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
    @patch('api.apps.ApiConfig.check_and_create_service_admin')
    def test_ready_silent_run(self, mock_create, mock_status):
        """Test that ready functions are not called."""
        mock_create.assert_not_called()
        mock_status.assert_not_called()

    def test_check_service_admin(self):
        """Test the check and create of service admin."""
        User.objects.all().delete()
        service_email = ENVIRONMENT.get_value('SERVICE_ADMIN_EMAIL',
                                              default='admin@example.com')
        self.assertTrue(User.objects.filter(
            email=service_email).count() == 0)
        api_config = apps.get_app_config('api')
        api_config.check_and_create_service_admin()
        self.assertTrue(User.objects.filter(
            email=service_email).count() != 0)

    def test_check_service_admin_exists(self):
        """Test the check and proceed of the service admin."""
        User.objects.all().delete()
        service_email = ENVIRONMENT.get_value('SERVICE_ADMIN_EMAIL',
                                              default='admin@example.com')
        service_user = ENVIRONMENT.get_value('SERVICE_ADMIN_USER',
                                             default='admin')
        service_pass = ENVIRONMENT.get_value('SERVICE_ADMIN_PASSWORD',
                                             default='pass')

        User.objects.create_superuser(service_user,
                                      service_email,
                                      service_pass)
        self.assertTrue(User.objects.filter(
            email=service_email).count() == 1)
        api_config = apps.get_app_config('api')
        api_config.check_and_create_service_admin()
        self.assertTrue(User.objects.filter(
            email=service_email).count() != 0)

    def test_create_service_admin(self):
        """Test the creation of the service admin."""
        service_email = ENVIRONMENT.get_value('SERVICE_ADMIN_EMAIL',
                                              default='admin@example.com')
        # An admin user is created using migratons.
        # Wipe it before testing creation.
        User.objects.filter(email=service_email).first().delete()
        api_config = apps.get_app_config('api')
        api_config.create_service_admin(service_email)
        self.assertTrue(User.objects.filter(
            email=service_email).count() != 0)

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

    # patching a method called by ApiConfig.ready()
    @patch.object(KokuApiConfig, 'check_and_create_service_admin',
                  lambda x: exec('raise ProgrammingError("This is a Test Exception")'))
    def test_catch_programming_error(self):
        """Test that we handle exceptions thrown when tables are missing."""
        api_config = apps.get_app_config('api')

        # the real test
        api_config.ready()

        # sanity-checking that the mocked object is raising the expected error
        with self.assertRaises(ProgrammingError):
            api_config.check_and_create_service_admin()
