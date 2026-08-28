"""Gunicorn configuration file."""
import faulthandler
import io
import multiprocessing
import sys
import threading
import traceback

import environ
from prometheus_client import multiprocess

from koku.feature_flags import UNLEASH_CLIENT
from koku.probe_server import BasicProbeServer
from koku.probe_server import start_probe_server


ENVIRONMENT = environ.Env()

CLOWDER_PORT = "8000"
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_PORT = LoadedConfig.publicPort

    if ENVIRONMENT.bool("MASU", default=False) or ENVIRONMENT.bool("SOURCES", default=False):
        CLOWDER_PORT = LoadedConfig.privatePort

# Logging (https://gunicorn.org/reference/settings/#logging)
loglevel = ENVIRONMENT.get_value("GUNICORN_LOG_LEVEL", default="DEBUG")
access_log_format = '%(h)s %(l)s %(u)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Security (https://gunicorn.org/reference/settings/#security)
# Allow HTTP headers up to this size
limit_request_field_size = 16380

# Control Socket (https://gunicorn.org/reference/settings/#control)
# Disable the control socket (gunicornc) to avoid PermissionError in containers
# where $HOME resolves to / (e.g. OpenShift random UIDs).
control_socket_disable = True

# Server Socket (https://gunicorn.org/reference/settings/#server-socket)
bind = f"0.0.0.0:{CLOWDER_PORT}"

# Worker Processes (https://gunicorn.org/reference/settings/#worker-processes)
cpu_resources = ENVIRONMENT.int("POD_CPU_LIMIT", default=multiprocessing.cpu_count())
workers = ENVIRONMENT.int("GUNICORN_WORKERS", default=(cpu_resources * 2 + 1))
gunicorn_threads = ENVIRONMENT.bool("GUNICORN_THREADS", default=False)
if gunicorn_threads:
    threads = cpu_resources * 2 + 1
timeout = ENVIRONMENT.int("TIMEOUT", default=100)
graceful_timeout = ENVIRONMENT.int("GRACEFUL_TIMEOUT", default=180)


# Server Hooks (https://gunicorn.org/reference/settings/#server-hooks)
def on_starting(server):
    """Called just before the main process is initialized."""
    httpd = start_probe_server(BasicProbeServer, server.log)
    httpd.RequestHandlerClass.ready = True


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    faulthandler.enable(file=sys.stderr, all_threads=True)
    UNLEASH_CLIENT.unleash_instance_id += f"_pid_{worker.pid}"
    worker.log.info("Initializing UNLEASH_CLIENT for gunicorn worker.")
    UNLEASH_CLIENT.initialize_client()


def _get_all_thread_stacks():
    """Return human-readable and Sentry-formatted stacks for every Python thread."""
    buffer = io.StringIO()
    threads_by_id = {thread.ident: thread for thread in threading.enumerate()}
    current_thread_id = threading.get_ident()
    sentry_threads = []

    for thread_id, frame in sys._current_frames().items():
        thread = threads_by_id.get(thread_id)
        thread_name = thread.name if thread else "unknown"
        buffer.write(f"Thread {thread_name} (id: {thread_id}):\n")
        traceback.print_stack(frame, file=buffer)

        frames = []
        for summary in traceback.extract_stack(frame):
            sentry_frame = {
                "filename": summary.filename,
                "function": summary.name,
                "lineno": summary.lineno,
            }
            if summary.line:
                sentry_frame["context_line"] = summary.line
            frames.append(sentry_frame)

        sentry_threads.append(
            {
                "id": thread_id,
                "name": thread_name,
                "current": thread_id == current_thread_id,
                "stacktrace": {"frames": frames},
            }
        )

    return buffer.getvalue(), sentry_threads


def _capture_worker_timeout(worker, sentry_threads):
    """Best-effort Sentry capture for a worker abort; never block its termination."""
    if not ENVIRONMENT.bool("KOKU_ENABLE_SENTRY", default=False):
        return

    try:
        import sentry_sdk

        sentry_sdk.capture_event(
            {
                "level": "error",
                "message": {"formatted": f"Gunicorn worker timeout (pid:{worker.pid})"},
                "tags": {"timeout": "hard"},
                "threads": {"values": sentry_threads},
            }
        )
        # Gunicorn exits immediately after this hook; give the async transport a
        # bounded opportunity to send the diagnostic event.
        sentry_sdk.flush(timeout=1)
    except Exception:
        worker.log.warning("Unable to send worker-timeout stack trace to Sentry.", exc_info=True)


def worker_abort(worker):
    """Log and, when possible, report all thread stacks for a worker timeout."""
    data, sentry_threads = _get_all_thread_stacks()

    worker.log.error(f"Killing worker (pid:{worker.pid})\n{data}")
    _capture_worker_timeout(worker, sentry_threads)


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
