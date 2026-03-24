#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Lightweight test settings for TDD without Postgres.

Usage (from koku/ directory)::

    DJANGO_SETTINGS_MODULE=koku.test_settings_lite \\
    DATABASE_SERVICE_NAME=POSTGRES_SQL POSTGRES_SQL_SERVICE_HOST=localhost \\
    POSTGRES_SQL_SERVICE_PORT=15432 prometheus_multiproc_dir=/tmp \\
    UNLEASH_HOST=localhost MIDDLEWARE_TIME_TO_LIVE=0 ENHANCED_ORG_ADMIN=True \\
    python -m unittest koku_rebac.test.test_config -v

Tests MUST use ``django.test.SimpleTestCase`` (no DB) or
``unittest.TestCase``.  Model-layer tests should mock the ORM.
"""
from koku.settings import *  # noqa: F401,F403
