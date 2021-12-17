#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Prometheus Stats."""
from prometheus_client import CollectorRegistry
from prometheus_client import Counter
from prometheus_client import Gauge
from prometheus_client import multiprocess


WORKER_REGISTRY = CollectorRegistry()
multiprocess.MultiProcessCollector(WORKER_REGISTRY)

GET_REPORT_ATTEMPTS_COUNTER = Counter(
    "get_report_files_attempts_count", "Number of ingest attempts", ["provider_type"], registry=WORKER_REGISTRY
)
REPORT_FILE_DOWNLOAD_ERROR_COUNTER = Counter(
    "report_file_download_error_count",
    "Number of report file download errors",
    ["provider_type"],
    registry=WORKER_REGISTRY,
)
PROCESS_REPORT_ATTEMPTS_COUNTER = Counter(
    "process_report_attempts_count",
    "Number of report files attempted processing",
    ["provider_type"],
    registry=WORKER_REGISTRY,
)
PROCESS_REPORT_ERROR_COUNTER = Counter(
    "process_report_error_count",
    "Number of report files attempted processing",
    ["provider_type"],
    registry=WORKER_REGISTRY,
)
REPORT_SUMMARY_ATTEMPTS_COUNTER = Counter(
    "report_summary_attempts_count", "Number of report summary attempts", ["provider_type"], registry=WORKER_REGISTRY
)
COST_MODEL_COST_UPDATE_ATTEMPTS_COUNTER = Counter(
    "charge_update_attempts_count", "Number of derivied cost update attempts", registry=WORKER_REGISTRY
)

COST_SUMMARY_ATTEMPTS_COUNTER = Counter(
    "cost_summary_attempts_count", "Number of cost summary update attempts", registry=WORKER_REGISTRY
)

KAFKA_CONNECTION_ERRORS_COUNTER = Counter(
    "kafka_connection_errors", "Number of Kafka connection errors", registry=WORKER_REGISTRY
)

CELERY_ERRORS_COUNTER = Counter("celery_errors", "Number of celery errors", registry=WORKER_REGISTRY)

DOWNLOAD_BACKLOG = Gauge(
    "download_backlog",
    "Number of celery tasks in the download queue",
    registry=WORKER_REGISTRY,
    multiprocess_mode="livesum",
)
SUMMARY_BACKLOG = Gauge(
    "summary_backlog",
    "Number of celery tasks in the summary queue",
    registry=WORKER_REGISTRY,
    multiprocess_mode="livesum",
)
PRIORITY_BACKLOG = Gauge(
    "priority_backlog",
    "Number of celery tasks in the priority queue",
    registry=WORKER_REGISTRY,
    multiprocess_mode="livesum",
)
REFRESH_BACKLOG = Gauge(
    "refresh_backlog",
    "Number of celery tasks in the refresh queue",
    registry=WORKER_REGISTRY,
    multiprocess_mode="livesum",
)
COST_MODEL_BACKLOG = Gauge(
    "cost_model_backlog",
    "Number of celery tasks in the cost model queue",
    registry=WORKER_REGISTRY,
    multiprocess_mode="livesum",
)
DEFAULT_BACKLOG = Gauge(
    "default_backlog",
    "Number of celery tasks in the default queue",
    registry=WORKER_REGISTRY,
    multiprocess_mode="livesum",
)
OCP_BACKLOG = Gauge(
    "ocp_backlog", "Number of celery tasks in the OCP queue", registry=WORKER_REGISTRY, multiprocess_mode="livesum"
)

HCS_BACKLOG = Gauge(
    "hcs_backlog", "Number of celery tasks in the HCS queue", registry=WORKER_REGISTRY, multiprocess_mode="livesum"
)

QUEUES = {
    "download": DOWNLOAD_BACKLOG,
    "summary": SUMMARY_BACKLOG,
    "priority": PRIORITY_BACKLOG,
    "refresh": REFRESH_BACKLOG,
    "cost_model": COST_MODEL_BACKLOG,
    "celery": DEFAULT_BACKLOG,
    "ocp": OCP_BACKLOG,
    "hcs": HCS_BACKLOG,
}

SOURCES_KAFKA_LOOP_RETRY = Counter(
    "sources_kafka_retry_errors", "Number of sources kafka retry errors", registry=WORKER_REGISTRY
)

SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER = Counter(
    "sources_provider_op_retry_errors", "Number of sources provider operation retry errors", registry=WORKER_REGISTRY
)

SOURCES_HTTP_CLIENT_ERROR_COUNTER = Counter(
    "sources_http_client_errors", "Number of sources http client errors", registry=WORKER_REGISTRY
)
