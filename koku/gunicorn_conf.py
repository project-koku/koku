"""Gunicorn configuration file."""
import io
import multiprocessing
import traceback

import environ
from prometheus_client import multiprocess

from koku.feature_flags import UNLEASH_CLIENT
from koku.probe_server import BasicProbeServer
from koku.probe_server import start_probe_server


ENVIRONMENT = environ.Env()

SOURCES = ENVIRONMENT.bool("SOURCES", default=False)

CLOWDER_PORT = "8000"
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_PORT = LoadedConfig.publicPort

    if ENVIRONMENT.bool("MASU", default=False) or ENVIRONMENT.bool("SOURCES", default=False):
        CLOWDER_PORT = LoadedConfig.privatePort

# Logging (https://docs.gunicorn.org/en/stable/settings.html#logging)
loglevel = ENVIRONMENT.get_value("GUNICORN_LOG_LEVEL", default="DEBUG")
access_log_format = '%(h)s %(l)s %(u)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Security (https://docs.gunicorn.org/en/stable/settings.html?highlight=limit_request_field_size#security)
# Allow HTTP headers up to this size
limit_request_field_size = 16380

# Server Socket (https://docs.gunicorn.org/en/stable/settings.html#server-socket)
bind = f"0.0.0.0:{CLOWDER_PORT}"

# Worker Processes (https://docs.gunicorn.org/en/stable/settings.html#worker-processes)
cpu_resources = ENVIRONMENT.int("POD_CPU_LIMIT", default=multiprocessing.cpu_count())
workers = ENVIRONMENT.int("GUNICORN_WORKERS", default=(cpu_resources * 2 + 1))
gunicorn_threads = ENVIRONMENT.bool("GUNICORN_THREADS", default=False)
if gunicorn_threads:
    threads = cpu_resources * 2 + 1
timeout = ENVIRONMENT.int("TIMEOUT", default=90)
graceful_timeout = ENVIRONMENT.int("GRACEFUL_TIMEOUT", default=180)


# Server Hooks (https://docs.gunicorn.org/en/stable/settings.html#server-hooks)
def on_starting(server):
    """Called just before the main process is initialized."""
    httpd = start_probe_server(BasicProbeServer, server.log)
    httpd.RequestHandlerClass.ready = True


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    UNLEASH_CLIENT.unleash_instance_id += f"_pid_{worker.pid}"
    worker.log.info("Initializing UNLEASH_CLIENT for gunicorn worker.")
    UNLEASH_CLIENT.initialize_client()


def worker_abort(worker):
    """Log the stack trace when a worker timeout occurs"""
    buffer = io.StringIO()
    traceback.print_stack(file=buffer)
    data = buffer.getvalue()
    buffer.close()

    worker.log.error(f"Killing worker (pid:{worker.pid})\n{data}")


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
