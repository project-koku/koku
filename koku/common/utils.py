# import functools
# import logging
# import random
# import time
# import typing as t
#
# from api.common import log_json
# from koku import settings
#
# LOG = logging.getLogger(__name__)
#
#
# def extract_context_from_sql_params(sql_params: dict[str, t.Any]) -> dict[str, t.Any]:
#     ctx = {}
#     if sql_params is None:
#         return ctx
#     if schema := sql_params.get("schema"):
#         ctx["schema"] = schema
#     if (start := sql_params.get("start")) or (start := sql_params.get("start_date")):
#         ctx["start_date"] = start
#     if (end := sql_params.get("end")) or (end := sql_params.get("end_date")):
#         ctx["end_date"] = end
#     if invoice_month := sql_params.get("invoice_month"):
#         ctx["invoice_month"] = invoice_month
#     if provider_uuid := sql_params.get("source_uuid"):
#         ctx["provider_uuid"] = provider_uuid
#     if cluster_id := sql_params.get("cluster_id"):
#         ctx["cluster_id"] = cluster_id
#
#     return ctx
#
#
# def retry(
#     original_callable: t.Callable = None,
#     *,
#     retries: int = settings.HIVE_PARTITION_DELETE_RETRIES,
#     retry_on: type[Exception] | tuple[type[Exception], ...] = Exception,
#     max_wait: int = 30,
#     log_message: t.Optional[str] = "Retrying...",
# ):
#     """Decorator with the retry logic."""
#
#     def _retry(callable: t.Callable):
#         @functools.wraps(callable)
#         def wrapper(*args, **kwargs):
#             context = kwargs.get("context", extract_context_from_sql_params(kwargs.get("sql_params", {}))) or None
#             for attempt in range(retries + 1):
#                 try:
#                     LOG.debug(f"Attempt {attempt + 1} for {callable.__name__}")
#                     return callable(*args, **kwargs)
#
#                 # The retry_on parameter can be a single exception or a tuple of exceptions
#                 except retry_on as ex:
#                     LOG.debug(f"Exception caught: {ex}")
#
#                     passed_check = True
#                     try:
#                         # Check if the exception has this Hive Metastore error
#                         # If it has, the except block will be passed
#                         # and the retry will be attempted
#                         passed_check = getattr(ex, "error_name") == "HIVE_METASTORE_ERROR"
#                     except (TypeError, AttributeError):
#                         pass
#
#                     # If the exception has the error_name attribute
#                     # and there are attempts left, retry
#                     if passed_check and attempt < retries:
#                         LOG.warning(
#                             log_json(
#                                 msg=f"{log_message} (attempt {attempt + 1})",
#                                 context=context,
#                                 exc_info=ex,
#                             )
#                         )
#                         backoff = min(2**attempt, max_wait)
#                         jitter = random.uniform(0, 1)
#                         delay = backoff + jitter
#                         LOG.debug(f"Sleeping for {delay} seconds before retrying")
#                         time.sleep(delay)
#                         continue
#
#                     LOG.error(
#                         log_json(
#                             msg=f"Failed execution after {attempt + 1} attempts",
#                             context=context,
#                             exc_info=ex,
#                         )
#                     )
#
#                     raise
#
#         return wrapper
#
#     if original_callable:
#         return _retry(original_callable)
#
#     return _retry
