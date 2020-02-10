#
# Copyright 2019 Red Hat, Inc.
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
from subprocess import CompletedProcess
from subprocess import PIPE
from unittest.mock import ANY
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.db import InterfaceError
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from sources.api.status import ApplicationStatus
from sources.sources_http_client import SourcesHTTPClientError


@override_settings(ROOT_URLCONF="sources.urls")
class StatusAPITest(TestCase):
    """Test Cases for the Status API."""

    def setUp(self):
        """Test case setup."""
        super().setUp()
        logging.disable(logging.NOTSET)

    def test_status(self):
        """Test the status endpoint."""
        response = self.client.get(reverse("server-status"))
        body = response.data

        self.assertEqual(response.status_code, 200)

        self.assertIn("commit", body)
        self.assertIn("current_datetime", body)
        self.assertIn("database_status", body)
        self.assertIn("debug", body)
        self.assertIn("modules", body)
        self.assertIn("platform_info", body)
        self.assertIn("python_version", body)
        self.assertIn("sources_status", body)

        self.assertIsNotNone(body["commit"])
        self.assertIsNotNone(body["current_datetime"])
        self.assertIsNotNone(body["database_status"])
        self.assertIsNotNone(body["debug"])
        self.assertIsNotNone(body["modules"])
        self.assertIsNotNone(body["platform_info"])
        self.assertIsNotNone(body["python_version"])
        self.assertIsNotNone(body["sources_status"])

    @patch.dict(os.environ, {"OPENSHIFT_BUILD_COMMIT": "fake_commit_hash"})
    def test_commit_with_env(self):
        """Test the commit method via environment."""
        result = ApplicationStatus().commit
        self.assertEqual(result, "fake_commit_hash")

    @patch("sources.api.status.subprocess.run")
    @patch("sources.api.status.os.environ.get", return_value=dict())
    def test_commit_with_subprocess(self, mock_os, mock_subprocess):
        """Test the commit method via subprocess."""
        expected = "buildnum"

        args = {"args": ["git", "describe", "--always"], "returncode": 0, "stdout": bytes(expected, encoding="UTF-8")}
        mock_subprocess.return_value = Mock(spec=CompletedProcess, **args)

        result = ApplicationStatus().commit

        mock_os.assert_called_with("OPENSHIFT_BUILD_COMMIT", None)
        mock_subprocess.assert_called_with(args["args"], stdout=PIPE)
        self.assertEqual(result, expected)

    @patch("sources.api.status.subprocess.run")
    @patch("sources.api.status.os.environ.get", return_value=dict())
    def test_commit_with_subprocess_nostdout(self, mock_os, mock_subprocess):
        """Test the commit method via subprocess when stdout is none."""
        args = {"args": ["git", "describe", "--always"], "returncode": 0, "stdout": None}
        mock_subprocess.return_value = Mock(spec=CompletedProcess, **args)

        result = ApplicationStatus().commit

        mock_os.assert_called_with("OPENSHIFT_BUILD_COMMIT", None)
        mock_subprocess.assert_called_with(args["args"], stdout=PIPE)
        self.assertIsNone(result.stdout)

    @patch("sources.api.status.platform.uname")
    def test_platform_info(self, mock_platform):
        """Test the platform_info method."""
        platform_record = namedtuple("Platform", ["os", "version"])
        a_plat = platform_record("Red Hat", "7.4")
        mock_platform.return_value = a_plat
        result = ApplicationStatus().platform_info
        self.assertEqual(result["os"], "Red Hat")
        self.assertEqual(result["version"], "7.4")

    @patch("sources.api.status.sys.version")
    def test_python_version(self, mock_sys_ver):
        """Test the python_version method."""
        expected = "Python 3.6"
        mock_sys_ver.replace.return_value = expected
        result = ApplicationStatus().python_version
        self.assertEqual(result, expected)

    @patch("sources.api.status.SourcesHTTPClient.get_cost_management_application_type_id")
    def test_sources_status(self, mock_status):
        """Test the sources_backend method."""
        expected = "Cost Management Application ID: 2"
        mock_status.return_value = 2
        result = ApplicationStatus().sources_backend
        self.assertEqual(result, expected)

    @patch("sources.api.status.SourcesHTTPClient.get_cost_management_application_type_id")
    def test_sources_status_disconnected(self, mock_status):
        """Test the sources_backend method while not connected."""
        expected = "Not connected"
        mock_status.side_effect = SourcesHTTPClientError
        result = ApplicationStatus().sources_backend
        self.assertEqual(result, expected)

    @patch("sources.api.status.sys.modules")
    def test_modules(self, mock_modules):
        """Test the modules method."""
        expected = {"module1": "version1", "module2": "version2"}
        mod1 = Mock(__version__="version1")
        mod2 = Mock(__version__="version2")
        mock_modules.items.return_value = (("module1", mod1), ("module2", mod2))
        result = ApplicationStatus().modules
        self.assertEqual(result, expected)

    @patch("sources.api.status.LOG.info")
    def test_startup_with_modules(self, mock_logger):
        """Test the startup method with a module list."""
        ApplicationStatus().startup()
        mock_logger.assert_called_with(ANY, ANY)

    @patch("sources.api.status.ApplicationStatus.modules", new_callable=PropertyMock)
    def test_startup_without_modules(self, mock_mods):
        """Test the startup method without a module list."""
        mock_mods.return_value = {}
        expected = "INFO:sources.api.status:Modules: None"

        with self.assertLogs("sources.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(expected, logger.output)

    @patch("masu.external.date_accessor.DateAccessor.today")
    def test_get_datetime(self, mock_date):
        """Test the startup method for datetime."""
        mock_date_string = "2018-07-25 10:41:59.993536"
        mock_date_obj = datetime.strptime(mock_date_string, "%Y-%m-%d %H:%M:%S.%f")
        mock_date.return_value = mock_date_obj
        expected = f"INFO:sources.api.status:Current Date: {mock_date.return_value}"
        with self.assertLogs("sources.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(str(expected), logger.output)

    def test_get_debug(self):
        """Test the startup method for debug state."""
        expected = "INFO:sources.api.status:DEBUG enabled: {}".format(str(False))
        with self.assertLogs("sources.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(str(expected), logger.output)

    def test_database_status(self):
        """Test that fetching database status works."""
        expected = re.compile(r"INFO:sources.api.status:Database: \[{.*postgres.*}\]")
        with self.assertLogs("sources.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            results = None
            for line in logger.output:
                if not results:
                    results = expected.search(line)
            self.assertIsNotNone(results)

    def test_database_status_fail(self):
        """Test that fetching database handles errors."""
        expected = "WARNING:sources.api.status:Unable to connect to DB: "
        with patch("django.db.backends.utils.CursorWrapper") as mock_cursor:
            mock_cursor = mock_cursor.return_value.__enter__.return_value
            mock_cursor.execute.side_effect = InterfaceError()
            with self.assertLogs("sources.api.status", level="INFO") as logger:
                ApplicationStatus().startup()
                self.assertIn(expected, logger.output)
