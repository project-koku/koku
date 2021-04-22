"""Gunicorn configuration file."""
import multiprocessing

import environ

ENVIRONMENT = environ.Env()

bind = "unix:/var/run/koku/gunicorn.sock"
cpu_resources = ENVIRONMENT.int("POD_CPU_LIMIT", default=multiprocessing.cpu_count())
workers = cpu_resources * 2 + 1

timeout = ENVIRONMENT.int("TIMEOUT", default=90)
loglevel = ENVIRONMENT.get_value("LOG_LEVEL", default="INFO")
graceful_timeout = ENVIRONMENT.int("GRACEFUL_TIMEOUT", default=180)

gunicorn_threads = ENVIRONMENT.bool("GUNICORN_THREADS", default=False)

if gunicorn_threads:
    threads = cpu_resources * 2 + 1
