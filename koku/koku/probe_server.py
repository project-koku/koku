#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HTTP server for liveness/readiness probes."""
import json
import logging
import threading
from abc import ABC
from abc import abstractmethod
from http.server import HTTPServer

from prometheus_client.exposition import MetricsHandler

from koku.env import ENVIRONMENT
from masu.prometheus_stats import WORKER_REGISTRY


LOG = logging.getLogger(__name__)
CLOWDER_METRICS_PORT = 9000
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_METRICS_PORT = LoadedConfig.metricsPort


def start_probe_server(server_cls, logger=LOG):
    """Start the probe server."""
    httpd = HTTPServer(("0.0.0.0", CLOWDER_METRICS_PORT), server_cls)
    httpd.RequestHandlerClass.logger = logger

    def start_server():
        """Start a simple webserver serving path on port"""
        httpd.RequestHandlerClass.ready = False
        httpd.serve_forever()

    logger.info("starting liveness/readiness probe server")
    daemon = threading.Thread(name="probe_server", target=start_server)
    daemon.setDaemon(True)  # Set as a daemon so it will be killed once the main thread is dead.
    daemon.start()
    logger.info(f"liveness/readiness probe server started on port {httpd.server_port}")

    return httpd


class ProbeServer(ABC, MetricsHandler):
    """HTTP server for liveness/readiness probes."""

    logger = LOG
    ready = False
    registry = WORKER_REGISTRY

    def _set_headers(self, status):
        """Set the response headers."""
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()

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
        self.logger.info("%s", format % args)

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
