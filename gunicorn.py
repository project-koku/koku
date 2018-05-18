"""Gunicorn configuration file."""
import multiprocessing

BIND = 'unix:/var/run/masu/gunicorn.sock'
WORKERS = multiprocessing.cpu_count() * 2 + 1
