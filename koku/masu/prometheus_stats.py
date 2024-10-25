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
    "get_report_files_attempts_count", "Number of ingest attempts", ["provider_type"]
)
REPORT_FILE_DOWNLOAD_ERROR_COUNTER = Counter(
    "report_file_download_error_count",
    "Number of report file download errors",
    ["provider_type"],
)
PROCESS_REPORT_ATTEMPTS_COUNTER = Counter(
    "process_report_attempts_count",
    "Number of report files attempted processing",
    ["provider_type"],
)
PROCESS_REPORT_ERROR_COUNTER = Counter(
    "process_report_error_count",
    "Number of report files attempted processing",
    ["provider_type"],
)
REPORT_SUMMARY_ATTEMPTS_COUNTER = Counter(
    "report_summary_attempts_count", "Number of report summary attempts", ["provider_type"]
)
COST_MODEL_COST_UPDATE_ATTEMPTS_COUNTER = Counter(
    "charge_update_attempts_count", "Number of derivied cost update attempts"
)

COST_SUMMARY_ATTEMPTS_COUNTER = Counter("cost_summary_attempts_count", "Number of cost summary update attempts")

KAFKA_CONNECTION_ERRORS_COUNTER = Counter("kafka_connection_errors", "Number of Kafka connection errors")

CELERY_ERRORS_COUNTER = Counter("celery_errors", "Number of celery errors")

DOWNLOAD_BACKLOG = Gauge(
    "download_backlog",
    "Number of celery tasks in the download queue",
    multiprocess_mode="livesum",
)
DOWNLOAD_XL_BACKLOG = Gauge(
    "download_xl_backlog",
    "Number of celery tasks in the download_xl queue",
    multiprocess_mode="livesum",
)
DOWNLOAD_PENALTY_BACKLOG = Gauge(
    "download_penalty_backlog",
    "Number of celery tasks in the download_penalty queue",
    multiprocess_mode="livesum",
)
SUMMARY_BACKLOG = Gauge(
    "summary_backlog",
    "Number of celery tasks in the summary queue",
    multiprocess_mode="livesum",
)
SUMMARY_XL_BACKLOG = Gauge(
    "summary_xl_backlog",
    "Number of celery tasks in the summary_xl queue",
    multiprocess_mode="livesum",
)
SUMMARY_PENALTY_BACKLOG = Gauge(
    "summary_penalty_backlog",
    "Number of celery tasks in the summary_penalty queue",
    multiprocess_mode="livesum",
)
PRIORITY_BACKLOG = Gauge(
    "priority_backlog",
    "Number of celery tasks in the priority queue",
    multiprocess_mode="livesum",
)
PRIORITY_XL_BACKLOG = Gauge(
    "priority_xl_backlog",
    "Number of celery tasks in the priority_xl queue",
    multiprocess_mode="livesum",
)
PRIORITY_PENALTY_BACKLOG = Gauge(
    "priority_penalty_backlog",
    "Number of celery tasks in the priority_penalty queue",
    multiprocess_mode="livesum",
)
REFRESH_BACKLOG = Gauge(
    "refresh_backlog",
    "Number of celery tasks in the refresh queue",
    multiprocess_mode="livesum",
)
REFRESH_XL_BACKLOG = Gauge(
    "refresh_xl_backlog",
    "Number of celery tasks in the refresh_xl queue",
    multiprocess_mode="livesum",
)
REFRESH_PENALTY_BACKLOG = Gauge(
    "refresh_penalty_backlog",
    "Number of celery tasks in the refresh_penalty queue",
    multiprocess_mode="livesum",
)
COST_MODEL_BACKLOG = Gauge(
    "cost_model_backlog",
    "Number of celery tasks in the cost_model queue",
    multiprocess_mode="livesum",
)
COST_MODEL_XL_BACKLOG = Gauge(
    "cost_model_xl_backlog",
    "Number of celery tasks in the cost_model_xl queue",
    multiprocess_mode="livesum",
)
COST_MODEL_PENALTY_BACKLOG = Gauge(
    "cost_model_penalty_backlog",
    "Number of celery tasks in the cost_model_penalty queue",
    multiprocess_mode="livesum",
)
DEFAULT_BACKLOG = Gauge(
    "default_backlog",
    "Number of celery tasks in the default queue",
    multiprocess_mode="livesum",
)
OCP_BACKLOG = Gauge("ocp_backlog", "Number of celery tasks in the OCP queue", multiprocess_mode="livesum")
OCP_XL_BACKLOG = Gauge(
    "ocp_xl_backlog",
    "Number of celery tasks in the OCP_xl queue",
    multiprocess_mode="livesum",
)
OCP_PENALTY_BACKLOG = Gauge(
    "ocp_penalty_backlog",
    "Number of celery tasks in the OCP_penalty queue",
    multiprocess_mode="livesum",
)

HCS_BACKLOG = Gauge("hcs_backlog", "Number of celery tasks in the HCS queue", multiprocess_mode="livesum")

SUBS_EXTRACTION_BACKLOG = Gauge(
    "subs_extraction_backlog",
    "Number of celery tasks in the SUBS Data Extraction queue",
    multiprocess_mode="livesum",
)

SUBS_TRANSMISSION_BACKLOG = Gauge(
    "subs_transmission_backlog",
    "Number of celery tasks in the SUBS Data Transmission queue",
    multiprocess_mode="livesum",
)

QUEUES = {
    "download": DOWNLOAD_BACKLOG,
    "download_xl": DOWNLOAD_XL_BACKLOG,
    "download_penalty": DOWNLOAD_PENALTY_BACKLOG,
    "summary": SUMMARY_BACKLOG,
    "summary_xl": SUMMARY_XL_BACKLOG,
    "summary_penalty": SUMMARY_PENALTY_BACKLOG,
    "priority": PRIORITY_BACKLOG,
    "priority_xl": PRIORITY_XL_BACKLOG,
    "priority_penalty": PRIORITY_PENALTY_BACKLOG,
    "refresh": REFRESH_BACKLOG,
    "refresh_xl": REFRESH_XL_BACKLOG,
    "refresh_penalty": REFRESH_PENALTY_BACKLOG,
    "cost_model": COST_MODEL_BACKLOG,
    "cost_model_xl": COST_MODEL_XL_BACKLOG,
    "cost_model_penalty": COST_MODEL_PENALTY_BACKLOG,
    "celery": DEFAULT_BACKLOG,
    "ocp": OCP_BACKLOG,
    "ocp_xl": OCP_XL_BACKLOG,
    "ocp_penalty": OCP_PENALTY_BACKLOG,
    "hcs": HCS_BACKLOG,
    "subs_extraction": SUBS_EXTRACTION_BACKLOG,
    "subs_transmission": SUBS_TRANSMISSION_BACKLOG,
}

SOURCES_KAFKA_LOOP_RETRY = Counter("sources_kafka_retry_errors", "Number of sources kafka retry errors")

SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER = Counter(
    "sources_provider_op_retry_errors", "Number of sources provider operation retry errors"
)

SOURCES_HTTP_CLIENT_ERROR_COUNTER = Counter("sources_http_client_errors", "Number of sources http client errors")

RHEL_ELS_VCPU_HOURS = Counter("rhel_els_vcpu_hours", "Number of RHEL ELS VCPU Hours", ["provider_type"])
RHEL_ELS_SYSTEMS_PROCESSED = Counter(
    "rhel_els_system_count", "Number of RHEL ELS systems processed", ["provider_type"]
)
