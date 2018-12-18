"""Gunicorn configuration file."""
import multiprocessing
import os

from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

BIND = 'unix:/var/run/masu/gunicorn.sock'
WORKERS = multiprocessing.cpu_count() * 2 + 1


def when_ready(server):  # pylint: disable=unused-argument
    """Start metrics server when gunicorn is ready."""
    GunicornPrometheusMetrics.start_http_server_when_ready(
        int(os.getenv('METRICS_PORT', default='9100')))


def child_exit(server, worker):  # pylint: disable=unused-argument
    """Mark process dead when gunicorn worker dies."""
    GunicornPrometheusMetrics.mark_process_dead_on_child_exit(worker.pid)
