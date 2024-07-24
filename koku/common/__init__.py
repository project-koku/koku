import functools
import logging
import random
import time
import typing as t

from api.common import log_json

LOG = logging.getLogger(__name__)


# class TrinoQueryError(Exception):
#     pass


def retry(
    original_callable: t.Callable = None,
    *,
    retries: int = 3,
    retry_on: tuple[t.Type[Exception], ...],
    attribute_to_check: str = "message",
    max_wait: int = 30,
    context_extractor: t.Optional[t.Callable] = None,
    log_ref: str = "Trino query",
    custom_exception: t.Type[Exception] = None,
    custom_log_message: t.Optional[str] = None,
):
    def _retry(callable: t.Callable):
        @functools.wraps(callable)
        def wrapper(*args, **kwargs):
            sql_params = kwargs.get("sql_params", {})
            if sql_params is None:
                sql_params = {}
            context = context_extractor(sql_params) if context_extractor else {}
            for attempt in range(retries + 1):
                try:
                    return callable(*args, **kwargs)
                except retry_on as ex:
                    if attempt < retries and "NoSuchKey" in getattr(ex, attribute_to_check, ""):
                        LOG.warning(
                            log_json(
                                msg=custom_log_message or "TrinoExternalError Exception, retrying...",
                                log_ref=log_ref,
                                context=context,
                            ),
                            exc_info=ex,
                        )
                        backoff = min(2**attempt, max_wait)
                        jitter = random.uniform(0, 1)
                        delay = backoff + jitter
                        time.sleep(delay)
                        continue

                    LOG.error(
                        log_json(
                            msg="Failed Trino SQL execution: TrinoExternalError", log_ref=log_ref, context=context
                        ),
                        exc_info=ex,
                    )
                    if custom_exception:
                        raise custom_exception(error=ex)
                    else:
                        raise ex

        return wrapper

    if original_callable:
        return _retry(original_callable)

    return _retry
