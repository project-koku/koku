#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os
import re

from api.iam.test.iam_test_case import IamTestCase


LOG = logging.getLogger(__name__)


class TestCheckMigrationDBFunc(IamTestCase):
    def setUp(self):
        self._log_db_pid_setting = os.environ.get("LOG_DB_PID")
        if self._log_db_pid_setting is not None:
            self._log_db_pid_setting = True if self._log_db_pid_setting.capitalize() == "True" else False

    def tearDown(self):
        if self._log_db_pid_setting is not None:
            os.environ["LOG_DB_PID"] = str(self._log_db_pid_setting)

    def test_log_ext_set(self):
        assert_method = self.assertTrue if self._log_db_pid_setting else self.assertFalse
        assert_method(hasattr(logging.Logger, "_log_o"))

    def test_dbpid_in_log(self):
        assert_method = self.assertRegexIn if self._log_db_pid_setting else self.assertRegexNotIn
        with self.assertLogs() as logger:
            LOG.warning("This is a test")
            assert_method(re.compile("DBPID_"), logger.output)
