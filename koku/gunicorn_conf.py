"""Gunicorn configuration file."""
import multiprocessing

import environ

from koku.probe_server import BasicProbeServer
from koku.probe_server import start_probe_server


ENVIRONMENT = environ.Env()

SOURCES = ENVIRONMENT.bool("SOURCES", default=False)

bind = "unix:/var/run/koku/gunicorn.sock"
cpu_resources = ENVIRONMENT.int("POD_CPU_LIMIT", default=multiprocessing.cpu_count())
workers = 1 if SOURCES else cpu_resources * 2 + 1

timeout = ENVIRONMENT.int("TIMEOUT", default=90)
loglevel = ENVIRONMENT.get_value("LOG_LEVEL", default="INFO")
graceful_timeout = ENVIRONMENT.int("GRACEFUL_TIMEOUT", default=180)

gunicorn_threads = ENVIRONMENT.bool("GUNICORN_THREADS", default=False)

if gunicorn_threads:
    threads = cpu_resources * 2 + 1


# Server Hooks
def on_starting(server):
    """gunicorn server hook to start probe server before main process"""
    httpd = start_probe_server(BasicProbeServer, server.log)
    httpd.RequestHandlerClass.ready = True
