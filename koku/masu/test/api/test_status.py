#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the status endpoint view."""
import logging
import re
from collections import namedtuple
from datetime import datetime
from unittest.mock import ANY
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.db import InterfaceError
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from masu.api import API_VERSION
from masu.api.status import ApplicationStatus
from masu.api.status import BROKER_CONNECTION_ERROR
from masu.api.status import CELERY_WORKER_NOT_FOUND


@override_settings(ROOT_URLCONF="masu.urls")
class StatusAPITest(TestCase):
    """Test Cases for the Status API."""

    def setUp(self):
        """Set up shared configuration."""
        super().setUp()
        logging.disable(logging.NOTSET)

    @patch("masu.api.status.RbacService")
    @patch("masu.api.status.ApplicationStatus.celery_status", new_callable=PropertyMock)
    def test_status(self, mock_celery, mock_rbac_service):
        """Test the status endpoint."""
        mock_celery.return_value = {"celery@koku_worker": {}}
        mock_rbac_service.return_value.get_cache_ttl.return_value = 30
        response = self.client.get(reverse("server-status"))
        body = response.data

        self.assertEqual(response.status_code, 200)

        self.assertIn("api_version", body)
        self.assertIn("celery_status", body)
        self.assertIn("commit", body)
        self.assertIn("config", body)
        self.assertIn("current_datetime", body)
        self.assertIn("database_status", body)
        self.assertIn("modules", body)
        self.assertIn("platform_info", body)
        self.assertIn("python_version", body)

        # Verify config fields
        self.assertIn("debug", body["config"])
        self.assertIn("masu_retain_num_months", body["config"])
        self.assertIn("rbac_cache_ttl", body["config"])

        self.assertEqual(body["api_version"], API_VERSION)
        self.assertIsNotNone(body["celery_status"])
        self.assertIsNotNone(body["commit"])
        self.assertIsNotNone(body["current_datetime"])
        self.assertIsNotNone(body["database_status"])
        self.assertIsNotNone(body["config"]["debug"])
        self.assertIsNotNone(body["config"]["masu_retain_num_months"])
        self.assertIsNotNone(body["modules"])
        self.assertIsNotNone(body["platform_info"])
        self.assertIsNotNone(body["python_version"])
        self.assertEqual(body["config"]["rbac_cache_ttl"], 30)

    @patch("masu.api.status.celery_app")
    def test_status_celery_param(self, mock_celery):
        """Test that celery counts are returned."""
        scheduled_tasks = [1, 2, 3]
        reserved_tasks = [3]
        active_tasks = []
        scheduled = {"task": scheduled_tasks}
        reserved = {"task": reserved_tasks}
        active = {"task": active_tasks}
        mock_inspect = mock_celery.control.inspect.return_value
        mock_inspect.scheduled.return_value = scheduled
        mock_inspect.reserved.return_value = reserved
        mock_inspect.active.return_value = active

        params = "?celery=true"
        url = reverse("server-status") + params
        response = self.client.get(url)
        body = response.data

        self.assertEqual(response.status_code, 200)

        self.assertIn("scheduled_count", body)
        self.assertIn("reserved_count", body)
        self.assertIn("active_count", body)

    @override_settings(GIT_COMMIT="buildnum")
    def test_commit(self):
        """Test the commit method via django settings."""
        expected = "buildnum"
        result = ApplicationStatus().commit
        self.assertEqual(result, expected)

    @patch("masu.api.status.platform.uname")
    def test_platform_info(self, mock_platform):
        """Test the platform_info method."""
        platform_record = namedtuple("Platform", ["os", "version"])
        a_plat = platform_record("Red Hat", "7.4")
        mock_platform.return_value = a_plat
        result = ApplicationStatus().platform_info
        self.assertEqual(result["os"], "Red Hat")
        self.assertEqual(result["version"], "7.4")

    @patch("masu.api.status.sys.version")
    def test_python_version(self, mock_sys_ver):
        """Test the python_version method."""
        expected = "Python 3.6"
        mock_sys_ver.replace.return_value = expected
        result = ApplicationStatus().python_version
        self.assertEqual(result, expected)

    @patch("masu.api.status.sys.modules")
    def test_modules(self, mock_modules):
        """Test the modules method."""
        expected = {"module1": "version1", "module2": "version2"}
        mod1 = Mock(__version__="version1")
        mod2 = Mock(__version__="version2")
        mock_modules.items.return_value = (("module1", mod1), ("module2", mod2))
        result = ApplicationStatus().modules
        self.assertEqual(result, expected)

    @patch("masu.api.status.celery_app")
    @patch("masu.api.status.LOG.info")
    def test_startup_with_modules(self, mock_logger, mock_celery):
        """Test the startup method with a module list."""
        ApplicationStatus().startup()
        mock_logger.assert_called_with(ANY, ANY)

    @patch("masu.api.status.celery_app")
    @patch("masu.api.status.ApplicationStatus.modules", new_callable=PropertyMock)
    def test_startup_without_modules(self, mock_mods, mock_celery):
        """Test the startup method without a module list."""
        mock_mods.return_value = {}
        expected = "INFO:masu.api.status:Modules: None"

        with self.assertLogs("masu.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(expected, logger.output)

    @patch("masu.api.status.celery_app")
    @patch("masu.api.status.DateHelper.now", new_callable=PropertyMock)
    def test_get_datetime(self, mock_date, mock_celery):
        """Test the startup method for datetime."""
        mock_date_string = "2018-07-25 10:41:59.993536"
        mock_date_obj = datetime.strptime(mock_date_string, "%Y-%m-%d %H:%M:%S.%f")
        mock_date.return_value = mock_date_obj
        expected = f"INFO:masu.api.status:Current Date: {mock_date.return_value}"
        with self.assertLogs("masu.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(str(expected), logger.output)

    @patch("masu.api.status.celery_app")
    def test_get_debug(self, mock_celery):
        """Test the startup method for debug state."""
        expected = f"INFO:masu.api.status:DEBUG enabled: {str(False)}"
        with self.assertLogs("masu.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(str(expected), logger.output)

    @patch("masu.api.status.celery_app")
    def test_startup_has_celery_status(self, mock_celery):
        """Test celery status is in startup() output."""
        expected_status = {"Status": "OK"}
        expected = f"INFO:masu.api.status:Celery Status: {expected_status}"

        mock_control = mock_celery.control
        mock_control.inspect.return_value.stats.return_value = expected_status

        with self.assertLogs("masu.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            self.assertIn(expected, logger.output)

    @patch("masu.api.status.celery_app")
    def test_celery_status(self, mock_celery):
        """Test that an error status is returned when Celery is down."""
        expected_status = {"Status": "OK"}
        mock_control = mock_celery.control
        mock_control.inspect.return_value.stats.return_value = expected_status

        status = ApplicationStatus().celery_status
        self.assertEqual(status, expected_status)

    @patch("masu.api.status.celery_app")
    def test_celery_status_no_stats(self, mock_celery):
        """Test that an error status is returned when Celery is down."""
        mock_control = mock_celery.control
        mock_control.inspect.return_value.stats.return_value = None

        expected_status = {"Error": CELERY_WORKER_NOT_FOUND}
        status = ApplicationStatus().celery_status
        self.assertEqual(status, expected_status)

    @patch("masu.api.status.celery_app")
    def test_celery_heartbeat_failure(self, mock_celery):
        """Test that heartbeat failure logs connection to broker issue."""
        mock_conn = mock_celery.connection.return_value
        mock_conn.heartbeat_check.side_effect = ConnectionRefusedError

        expected_status = {"Error": BROKER_CONNECTION_ERROR}
        status = ApplicationStatus().celery_status
        self.assertEqual(status, expected_status)

    @patch("masu.api.status.celery_app")
    def test_celery_status_connection_reset(self, mock_celery):
        """Test that the status retrys on connection reset."""
        mock_celery.control.inspect.side_effect = ConnectionResetError
        stat = ApplicationStatus()
        result = stat._check_celery_status()

        self.assertIn("Error", result)

        result = stat.celery_status

        self.assertIn("Error", result)
        # celery_app.control.inspect

    @patch("masu.api.status.celery_app")
    def test_database_status(self, mock_celery):
        """Test that fetching database status works."""
        expected = re.compile(r"INFO:masu.api.status:Database: \[{.*postgres.*}\]")
        with self.assertLogs("masu.api.status", level="INFO") as logger:
            ApplicationStatus().startup()
            results = None
            for line in logger.output:
                if not results:
                    results = expected.search(line)
            self.assertIsNotNone(results)

    @patch("masu.api.status.celery_app")
    def test_database_status_fail(self, mock_celery):
        """Test that fetching database handles errors."""
        expected = "WARNING:masu.api.status:Unable to connect to DB: "
        with patch("django.db.backends.utils.CursorWrapper") as mock_cursor:
            mock_cursor = mock_cursor.return_value.__enter__.return_value
            mock_cursor.execute.side_effect = InterfaceError()
            with self.assertLogs("masu.api.status", level="INFO") as logger:
                ApplicationStatus().startup()
                self.assertIn(expected, logger.output)

    @patch("masu.api.status.celery_app")
    def test_get_celery_queue_data(self, mock_celery):
        """Test that queue results are returned."""
        scheduled_tasks = [1, 2, 3]
        reserved_tasks = [3]
        active_tasks = []
        scheduled = {"task": scheduled_tasks}
        reserved = {"task": reserved_tasks}
        active = {"task": active_tasks}
        mock_inspect = mock_celery.control.inspect.return_value
        mock_inspect.scheduled.return_value = scheduled
        mock_inspect.reserved.return_value = reserved
        mock_inspect.active.return_value = active

        stat = ApplicationStatus()
        result = stat.celery_task_status

        self.assertIn("scheduled_count", result)
        self.assertIn("reserved_count", result)
        self.assertIn("active_count", result)

        self.assertEqual(result["scheduled_count"], len(scheduled_tasks))
        self.assertEqual(result["reserved_count"], len(reserved_tasks))
        self.assertEqual(result["active_count"], len(active_tasks))

    @patch("masu.api.status.celery_app")
    def test_get_celery_queue_data_error(self, mock_celery):
        """Test that queue results are returned."""
        mock_inspect = mock_celery.control.inspect.return_value
        mock_inspect.scheduled.side_effect = ConnectionResetError

        stat = ApplicationStatus()
        result = stat.celery_task_status

        self.assertIn("Error", result)
