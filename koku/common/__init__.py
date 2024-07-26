import functools
import logging
import random
import time
import typing as t

from api.common import log_json
from common.util import extract_context_from_sql_params

LOG = logging.getLogger(__name__)


def retry(
    original_callable: t.Callable = None,
    *,
    retries: int = 3,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    attribute_to_check: str = "message",
    max_wait: int = 30,
    log_ref: str = "Trino query",
    log_message: t.Optional[str] = "Retrying...",
):
    def _retry(callable: t.Callable):
        @functools.wraps(callable)
        def wrapper(*args, **kwargs):
            context = kwargs.get("context", extract_context_from_sql_params(kwargs.get("sql_params", {}))) or None
            for attempt in range(retries + 1):
                try:
                    LOG.debug(f"Attempt {attempt + 1} for {callable.__name__}")
                    return callable(*args, **kwargs)
                except retry_on as ex:
                    LOG.debug(f"Exception caught: {ex}")
                    if attempt < retries:
                        LOG.warning(
                            log_json(
                                msg=f"{log_message} (attempt {attempt + 1})",
                                context=context,
                                exc_info=ex,
                            )
                        )
                        backoff = min(2**attempt, max_wait)
                        jitter = random.uniform(0, 1)
                        delay = backoff + jitter
                        LOG.debug(f"Sleeping for {delay} seconds before retrying")
                        time.sleep(delay)
                        continue

                    LOG.error(
                        log_json(
                            msg=f"Failed execution after {attempt + 1} attempts",
                            context=context,
                            exc_info=ex,
                        )
                    )

                    raise

        return wrapper

    if original_callable:
        return _retry(original_callable)

    return _retry
