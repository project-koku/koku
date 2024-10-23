#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Prometheus metrics."""
from prometheus_client import CollectorRegistry
from prometheus_client import Counter
from prometheus_client import multiprocess

REGISTRY = CollectorRegistry()
multiprocess.MultiProcessCollector(REGISTRY)
DB_CONNECTION_ERRORS_COUNTER = Counter("db_connection_errors", "Number of DB connection errors")
