import functools
import logging
import random
import time
import typing as t

LOG = logging.getLogger(__name__)


def retry(
    original_callable: t.Callable = None,
    *,
    retries: int = 3,
    retry_on: tuple[t.Type[Exception], ...] = (Exception,),
    attribute_to_check: str = "message",
    max_wait: int = 30,
    context_extractor: t.Optional[t.Callable] = None,
    log_ref: str = "Trino query",
    custom_exception: t.Type[Exception] = None,
    log_message: t.Optional[str] = "Retrying...",
):
    def _retry(callable: t.Callable):
        @functools.wraps(callable)
        def wrapper(*args, **kwargs):
            for attempt in range(retries + 1):
                try:
                    LOG.debug(f"Attempt {attempt + 1} for {callable.__name__}")
                    return callable(*args, **kwargs)
                except retry_on as ex:
                    LOG.debug(f"Exception caught: {ex}")
                    if attempt < retries:
                        LOG.warning(
                            f"{log_message} (attempt {attempt + 1})",
                            exc_info=ex,
                        )
                        backoff = min(2**attempt, max_wait)
                        jitter = random.uniform(0, 1)
                        delay = backoff + jitter
                        LOG.debug(f"Sleeping for {delay} seconds before retrying")
                        time.sleep(delay)
                        continue

                    LOG.error(
                        f"Failed execution after {attempt + 1} attempts",
                        exc_info=ex,
                    )
                    if custom_exception:
                        raise custom_exception(error=ex) from ex
                    else:
                        raise ex

        return wrapper

    if original_callable:
        return _retry(original_callable)

    return _retry
