"""Sentry configuration file for the Koku project."""
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


def before_send(event, hint):
    from koku.middleware import RequestTimeoutError

    exc_info = hint.get("exc_info")
    if exc_info and exc_info[0] is RequestTimeoutError:
        event.setdefault("tags", {})["timeout"] = "soft"
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
