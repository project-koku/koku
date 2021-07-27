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
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer

from koku.env import ENVIRONMENT


LOG = logging.getLogger(__name__)
CLOWDER_PORT = 9000
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_PORT = LoadedConfig.publicPort


def start_probe_server(server_cls):
    """Start the probe server."""
    httpd = HTTPServer(("0.0.0.0", CLOWDER_PORT), server_cls)

    def start_server():
        """Start a simple webserver serving path on port"""
        httpd.RequestHandlerClass.ready = False
        httpd.serve_forever()

    LOG.info("starting liveness/readiness probe server")
    daemon = threading.Thread(name="probe_server", target=start_server)
    daemon.setDaemon(True)  # Set as a daemon so it will be killed once the main thread is dead.
    daemon.start()
    LOG.info("liveness/readiness probe server started")

    return httpd


class ProbeServer(ABC, BaseHTTPRequestHandler):
    """HTTP server for liveness/readiness probes."""

    ready = False

    def __init__(self, *args, **kwargs):
        """Initialize the server."""
        self.logger = logging.getLogger(__name__)
        super().__init__(*args, **kwargs)

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

    @abstractmethod
    def readiness_check(self):
        """Set the readiness check response."""
        pass


class ProbeResponse:
    """ProbeResponse object for the probe server."""

    def __init__(self, status_code, msg):
        """Initialize the response object."""
        self.status_code = status_code
        self.json = json.dumps({"status": status_code, "msg": msg})
