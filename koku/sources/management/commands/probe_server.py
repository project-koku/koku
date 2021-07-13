#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HTTP server for liveness/readiness probes."""
import json
import logging
from http.server import BaseHTTPRequestHandler

from sources.api.status import check_kafka_connection
from sources.api.status import check_sources_connection


LOG = logging.getLogger(__name__)


class ProbeServer(BaseHTTPRequestHandler):
    """HTTP server for liveness/readiness probes."""

    ready = False

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

    def default_response(self):
        """Set the default response."""
        self._write_response(Response(404, "not found"))

    def liveness_check(self):
        """Set the liveness check response."""
        self._write_response(Response(200, "ok"))

    def readiness_check(self):
        """Set the readiness check response."""
        status = 424
        msg = "not ready"
        if self.ready:
            if not check_kafka_connection():
                self._write_response(Response(status, "kafka not ready"))
                return
            if not check_sources_connection():
                self._write_response(Response(status, "sources not ready"))
                return
            status = 200
            msg = "ok"
        self._write_response(Response(status, msg))

    def log_message(self, format, *args):
        """Basic log message."""
        LOG.info("%s", format % args)


class Response:
    """Response object for the probe server."""

    def __init__(self, status_code, msg):
        """Initialize the response object."""
        self.status_code = status_code
        self.json = json.dumps({"status": status_code, "msg": msg})
