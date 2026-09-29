#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HTTP server for liveness/readiness probes."""
import json
import logging
import threading
import time
from abc import ABC
from abc import abstractmethod
from http.server import HTTPServer
from typing import Any

from prometheus_client.exposition import MetricsHandler

from koku.env import ENVIRONMENT
from masu.prometheus_stats import WORKER_REGISTRY

# Parent-process heartbeat for WorkerProbeServer /livez. Updated by the Celery
# parent loop (wait_for_migrations + hub/timer), never by a daemon ticker thread.
_parent_heartbeat_at: float | None = None
# Kafka/sources consumer thread for ListenerProbeServer / SourcesProbeServer /livez.
_consumer_thread: threading.Thread | None = None


def get_probe_liveness_heartbeat_seconds() -> int:
    """Seconds after which a missing parent heartbeat fails worker /livez."""
    return ENVIRONMENT.int("PROBE_LIVENESS_HEARTBEAT_SECONDS", default=60)


def touch_parent_heartbeat() -> None:
    """Record that the Celery parent loop is still running."""
    global _parent_heartbeat_at
    _parent_heartbeat_at = time.monotonic()


def reset_parent_heartbeat() -> None:
    """Clear the parent heartbeat (tests)."""
    global _parent_heartbeat_at
    _parent_heartbeat_at = None


def parent_heartbeat_is_fresh(*, now: float | None = None) -> bool:
    """Return True if the parent heartbeat was touched within the threshold."""
    if _parent_heartbeat_at is None:
        return False
    current = time.monotonic() if now is None else now
    return (current - _parent_heartbeat_at) < get_probe_liveness_heartbeat_seconds()


def install_parent_heartbeat(timer: Any) -> None:
    """Register a recurring parent heartbeat on the Celery hub/timer.

    `timer` must expose `call_repeatedly(interval, callback)` and be driven by
    the same parent event loop that would freeze if the worker is wedged.
    Do not pass a dedicated daemon thread.
    """
    touch_parent_heartbeat()
    interval = max(get_probe_liveness_heartbeat_seconds() // 3, 1)
    timer.call_repeatedly(interval, touch_parent_heartbeat)


def register_consumer_thread(thread: threading.Thread | None) -> None:
    """Record the Kafka/sources consumer thread for listener /livez checks."""
    global _consumer_thread
    _consumer_thread = thread


def reset_consumer_thread() -> None:
    """Clear the registered consumer thread (tests)."""
    global _consumer_thread
    _consumer_thread = None


def consumer_thread_is_alive() -> bool:
    """Return True if a consumer thread is registered and still running."""
    return _consumer_thread is not None and _consumer_thread.is_alive()


def parent_heartbeat_liveness_response(ready: bool) -> "ProbeResponse":
    """HTTP status for worker /livez from heartbeat freshness and startup state."""
    if not ready or parent_heartbeat_is_fresh():
        return ProbeResponse(200, "ok")
    return ProbeResponse(503, "parent heartbeat stale")


def consumer_thread_liveness_response(ready: bool) -> "ProbeResponse":
    """HTTP status for listener /livez from consumer thread liveness and startup state."""
    if not ready or consumer_thread_is_alive():
        return ProbeResponse(200, "ok")
    return ProbeResponse(503, "consumer thread not alive")


LOG = logging.getLogger(__name__)
CLOWDER_METRICS_PORT = 9000
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_METRICS_PORT = LoadedConfig.metricsPort

SERVER_TYPE = "liveness/readiness/metrics"
if ENVIRONMENT.bool("MASU", default=False) or ENVIRONMENT.bool("SOURCES", default=False):
    SERVER_TYPE = "metrics"


def start_probe_server(server_cls, logger=LOG):
    """Start the probe server."""
    httpd = HTTPServer(("0.0.0.0", CLOWDER_METRICS_PORT), server_cls)
    httpd.RequestHandlerClass.logger = logger

    def start_server():
        """Start a simple webserver serving path on port"""
        httpd.RequestHandlerClass.ready = False
        httpd.serve_forever()

    logger.info(f"starting {SERVER_TYPE} probe server")
    daemon = threading.Thread(name="probe_server", target=start_server)
    daemon.setDaemon(True)  # Set as a daemon so it will be killed once the main thread is dead.
    daemon.start()
    logger.info(f"{SERVER_TYPE} probe server started on port {httpd.server_port}")

    return httpd


class ProbeServer(ABC, MetricsHandler):
    """HTTP server for liveness/readiness probes."""

    logger = LOG
    log_level = None
    ready = False
    registry = WORKER_REGISTRY

    def _set_headers(self, status):
        """Set the response headers."""
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def _set_log_level(self, status_code):
        """Set the log level."""
        self.log_level = logging.DEBUG if status_code == 200 else logging.WARNING

    def _write_response(self, response):
        """Write the response to the client."""
        self._set_headers(response.status_code)
        self.wfile.write(response.json.encode("utf-8"))

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/livez":
            self.liveness_check()
        elif self.path == "/readyz":
            self.readiness_check()
        elif self.path == "/metrics":
            self.metrics_check()
        else:
            self.default_response()

    def log_message(self, format, *args):
        """Basic log message."""
        log_level = self.log_level or logging.WARNING
        self.logger.log(log_level, "%s", format % args)

    def send_response(self, code, message=None):
        """Send the response."""
        self._set_log_level(code)
        super().send_response(code, message)

    def default_response(self):
        """Set the default response."""
        self._write_response(ProbeResponse(404, "not found"))

    def liveness_check(self):
        """Set the liveness check response."""
        self._write_response(ProbeResponse(200, "ok"))

    def metrics_check(self):
        """Get the metrics."""
        super().do_GET()

    @abstractmethod
    def readiness_check(self):
        """Set the readiness check response."""
        pass


class BasicProbeServer(ProbeServer):
    """HTTP server for liveness/readiness probes."""

    def readiness_check(self):
        """Set the readiness check response."""
        status = 424
        msg = "not ready"
        if self.ready:
            status = 200
            msg = "ok"
        self._write_response(ProbeResponse(status, msg))


class ProbeResponse:
    """ProbeResponse object for the probe server."""

    def __init__(self, status_code, msg):
        """Initialize the response object."""
        self.status_code = status_code
        self.json = json.dumps({"status": status_code, "msg": msg})
