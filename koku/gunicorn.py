"""Gunicorn configuration file."""
import multiprocessing
import os

bind = 'unix:/var/run/koku/gunicorn.sock'
workers = multiprocessing.cpu_count() * 2 + 1
timeout = int(os.environ.get('TIMEOUT', '90'))