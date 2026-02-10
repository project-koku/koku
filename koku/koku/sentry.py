"""Sentry configuration file for the Koku project."""
import re

import sentry_sdk

from .env import ENVIRONMENT

BLOCK_LIST = {
    "/api/cost-management/v1/status/",
    "/api/cost-management/v1/source-status/",
}


def traces_sampler(sampling_context):
    wsgi_environ = sampling_context.get("wsgi_environ")
    if wsgi_environ and wsgi_environ.get("PATH_INFO") in BLOCK_LIST:
        # Drop this transaction, by setting its sample rate to 0%
        return 0

    # Default sample rate for all others (replaces traces_sample_rate)
    return 0.05


def _extract_pid(message):
    """Extract PID from timeout/kill messages."""
    # Matches: "(pid:123)", "pid:123"
    match = re.search(r"pid:(\d+)", message.lower())
    return match.group(1) if match else None


def before_send(event, hint):
    """Group timeout/OOM errors by PID for api-reads workers."""
    # Get message from either logentry or message field
    message = (event.get("logentry") or {}).get("formatted") or event.get("message") or ""
    message_lower = message.lower() if isinstance(message, str) else ""

    # Check for worker timeout or OOM
    keywords = ["worker timeout", "killing worker", "out of memory"]
    if any(kw in message_lower for kw in keywords):
        server_name = event.get("server_name", "")

        if "api-reads" in server_name:
            if pid := _extract_pid(message):
                event["fingerprint"] = [f"worker-timeout-api-reads-pid-{pid}"]

    return event


if ENVIRONMENT.bool("KOKU_ENABLE_SENTRY", default=False):
    sentry_sdk.init(
        dsn=ENVIRONMENT("KOKU_SENTRY_DSN"),
        environment=ENVIRONMENT("KOKU_SENTRY_ENVIRONMENT"),
        traces_sampler=traces_sampler,
        before_send=before_send,
    )
    print("Sentry setup.")
else:
    print("Sentry not enabled.")
