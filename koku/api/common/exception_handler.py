#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common exception handler class."""
import copy

from rest_framework.views import exception_handler


def _generate_errors_from_list(data, **kwargs):
    """Create error objects based on the exception."""
    errors = []
    status_code = kwargs.get("status_code", 0)
    source = kwargs.get("source")
    for value in data:
        if isinstance(value, str):
            new_error = {"detail": value, "source": source, "status": status_code}
            errors.append(new_error)
        elif isinstance(value, list):
            errors += _generate_errors_from_list(value, **kwargs)
        elif isinstance(value, dict):
            errors += _generate_errors_from_dict(value, **kwargs)
    return errors


def _generate_errors_from_dict(data, **kwargs):
    """Create error objects based on the exception."""
    errors = []
    status_code = kwargs.get("status_code", 0)
    source = kwargs.get("source")
    for key, value in data.items():
        source_val = f"{source}.{key}" if source else key
        if isinstance(value, str):
            new_error = {"detail": value, "source": source_val, "status": status_code}
            errors.append(new_error)
        elif isinstance(value, list):
            kwargs["source"] = source_val
            errors += _generate_errors_from_list(value, **kwargs)
        elif isinstance(value, dict):
            kwargs["source"] = source_val
            errors += _generate_errors_from_dict(value, **kwargs)
    return errors


def custom_exception_handler(exc, context):
    """Create custom response for exceptions."""
    response = exception_handler(exc, context)

    # Now add the HTTP status code to the response.
    if response is not None:
        errors = []
        data = copy.deepcopy(response.data)
        if isinstance(data, dict):
            errors += _generate_errors_from_dict(data, **{"status_code": response.status_code})
        elif isinstance(data, list):
            errors += _generate_errors_from_list(data, **{"status_code": response.status_code})
        error_response = {"errors": errors}
        response.data = error_response

    return response
