"""Tests for celery startup."""
from unittest.mock import Mock
from unittest.mock import patch

from koku.celery import init_worker
from masu.test import MasuTestCase


@patch("koku.feature_flags.UNLEASH_CLIENT.initialize_client", Mock())
class TestCeleryStartup(MasuTestCase):
    """Test cases for Celery tasks."""

    def test_unleash_init(self):
        with self.assertLogs() as logger:
            init_worker()
            pre_found = post_found = False
            for line in logger.output:
                if not pre_found:
                    pre_found = "Initializing UNLEASH_CLIENT for celery worker." in line
                elif not post_found:
                    post_found = "UNLEASH_CLIENT initialized for celery worker in" in line
                else:
                    break

        self.assertTrue(pre_found, "Log pre-init not found")
        self.assertTrue(post_found, "Log post-init not found")
