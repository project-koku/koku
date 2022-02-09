"""Gunicorn configuration file."""
import multiprocessing

import environ

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

bind = f"0.0.0.0:{CLOWDER_PORT}"

cpu_resources = ENVIRONMENT.int("POD_CPU_LIMIT", default=multiprocessing.cpu_count())
workers = 1 if SOURCES else cpu_resources * 2 + 1

timeout = ENVIRONMENT.int("TIMEOUT", default=90)
loglevel = ENVIRONMENT.get_value("GUNICORN_LOG_LEVEL", default="INFO")
graceful_timeout = ENVIRONMENT.int("GRACEFUL_TIMEOUT", default=180)

gunicorn_threads = ENVIRONMENT.bool("GUNICORN_THREADS", default=False)

if gunicorn_threads:
    threads = cpu_resources * 2 + 1


# Server Hooks
def on_starting(server):
    """Called just before the main process is initialized."""
    httpd = start_probe_server(BasicProbeServer, server.log)
    httpd.RequestHandlerClass.ready = True


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    UNLEASH_CLIENT.unleash_instance_id += f"_pid_{worker.pid}"
    worker.log.info("Initializing UNLEASH_CLIENT for gunicorn worker.")
    UNLEASH_CLIENT.initialize_client()


def worker_exit(server, worker):
    """Called just after a worker has been exited, in the worker process."""
    worker.log.info("Shutting down UNLEASH_CLIENT for gunicorn worker.")
    UNLEASH_CLIENT.destroy()
