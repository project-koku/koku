#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test that the forecast module does not load statsmodels at import time."""
import os
import subprocess
import sys

from django.test import SimpleTestCase


class ForecastLazyImportTest(SimpleTestCase):
    """Django's URL checks import forecast.forecast in every process, including Celery workers."""

    def test_import_does_not_load_statsmodels(self):
        """Importing the forecast module must not import statsmodels (~150 MB)."""
        code = (
            "import sys, django; django.setup(); import forecast.forecast; "
            "sys.exit(1 if any(m.split('.')[0] == 'statsmodels' for m in sys.modules) else 0)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=os.environ | {"DJANGO_SETTINGS_MODULE": "koku.settings"},
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
