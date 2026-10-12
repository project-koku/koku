#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test OCP download utility functions."""
from unittest.mock import Mock

import requests

from masu.external.downloader.ocp.download import is_permanent_download_error
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.test import MasuTestCase


class TestIsPermanentDownloadError(MasuTestCase):
    """Test is_permanent_download_error function."""

    def test_size_limit_violation_is_permanent(self):
        """Test that size limit violations are treated as permanent failures."""
        error = KafkaMsgHandlerError(
            "Unable to download file. Download exceeded maximum allowed size of 5368709120 bytes."
        )
        self.assertTrue(is_permanent_download_error(error))

    def test_time_limit_violation_is_permanent(self):
        """Test that time limit violations are treated as permanent failures."""
        error = KafkaMsgHandlerError("Unable to download file. Download exceeded total time limit of 900 seconds.")
        self.assertTrue(is_permanent_download_error(error))

    def test_http_4xx_error_is_permanent(self):
        """Test that HTTP 4xx errors (except 408, 429) are permanent."""
        # Mock HTTP 404 error
        response = Mock()
        response.status_code = 404
        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        error = KafkaMsgHandlerError("Unable to download file. Error: HTTPError")
        error.__cause__ = http_error

        self.assertTrue(is_permanent_download_error(error))

    def test_http_408_is_rewindable(self):
        """Test that HTTP 408 errors are not permanent (rewindable)."""
        response = Mock()
        response.status_code = 408
        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        error = KafkaMsgHandlerError("Unable to download file. Error: HTTPError")
        error.__cause__ = http_error

        self.assertFalse(is_permanent_download_error(error))

    def test_http_429_is_rewindable(self):
        """Test that HTTP 429 errors are not permanent (rewindable)."""
        response = Mock()
        response.status_code = 429
        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        error = KafkaMsgHandlerError("Unable to download file. Error: HTTPError")
        error.__cause__ = http_error

        self.assertFalse(is_permanent_download_error(error))

    def test_http_5xx_error_is_not_permanent(self):
        """Test that HTTP 5xx errors are not permanent (server issues)."""
        response = Mock()
        response.status_code = 500
        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        error = KafkaMsgHandlerError("Unable to download file. Error: HTTPError")
        error.__cause__ = http_error

        self.assertFalse(is_permanent_download_error(error))

    def test_non_http_error_is_not_permanent(self):
        """Test that non-HTTP errors without size/time messages are not permanent."""
        error = KafkaMsgHandlerError("Some other error message")
        self.assertFalse(is_permanent_download_error(error))

    def test_connection_error_is_not_permanent(self):
        """Test that connection errors are not permanent (transient network issues)."""
        connection_error = requests.exceptions.ConnectionError("Connection failed")
        error = KafkaMsgHandlerError("Unable to download file. Error: ConnectionError")
        error.__cause__ = connection_error

        self.assertFalse(is_permanent_download_error(error))
