"""Gunicorn configuration file."""
import multiprocessing
import os

import environ

ENVIRONMENT = environ.Env()

SOURCES = ENVIRONMENT.bool('SOURCES', default=False)

bind = 'unix:/var/run/koku/gunicorn.sock'
cpu_resources = int(os.environ.get('POD_CPU_LIMIT', multiprocessing.cpu_count()))
workers = 1 if SOURCES else cpu_resources * 2
threads = 10
timeout = int(os.environ.get('TIMEOUT', '90'))
loglevel = os.environ.get('LOG_LEVEL', 'INFO')
graceful_timeout = int(os.environ.get('GRACEFUL_TIMEOUT', '180'))
