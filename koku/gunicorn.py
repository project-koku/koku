"""Gunicorn configuration file."""
import multiprocessing

import environ

ENVIRONMENT = environ.Env()

SOURCES = ENVIRONMENT.bool("SOURCES", default=False)

bind = "unix:/var/run/koku/gunicorn.sock"
cpu_resources = ENVIRONMENT.int("POD_CPU_LIMIT", default=multiprocessing.cpu_count())
workers = 1 if SOURCES else cpu_resources * 2 + 1
timeout = ENVIRONMENT.int("TIMEOUT", default=120)
loglevel = ENVIRONMENT.get_value("LOG_LEVEL", default="INFO")
graceful_timeout = ENVIRONMENT.int("GRACEFUL_TIMEOUT", default=180)
