#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Output sanitization utilities for API responses.

This module provides sanitization functions for data output in API responses
to prevent XSS attacks and ensure safe handling of user-controlled data in URLs.
"""
import html
import re
from typing import Any
from urllib.parse import quote


# Fields that may contain user-controlled data requiring sanitization
OCP_USER_CONTROLLED_FIELDS = {
    "namespace",
    "project",  # project is an alias for namespace in API
    "pod",
    "node",
    "cluster",
    "cluster_id",
    "cluster_alias",
    "persistentvolumeclaim",
    "persistentvolume",
    "storageclass",
    "resource_id",
}

# Fields that are used in URL parameters
URL_PARAMETER_FIELDS = {
    "namespace",
    "project",
    "pod",
    "node",
    "cluster",
    "cluster_id",
    "persistentvolumeclaim",
    "persistentvolume",
}


def sanitize_for_html(value: str) -> str:
    """
    Sanitize a string value for safe HTML output.

    Encodes special HTML characters to prevent XSS attacks.

    Args:
        value: The string value to sanitize.

    Returns:
        The HTML-safe string.
    """
    if not isinstance(value, str):
        return value

    return html.escape(value, quote=True)


def sanitize_for_url(value: str) -> str:
    """
    URL encode a value for safe use in URLs.

    This is particularly useful for values used in URL parameters
    like project names in the Cost Management UI.

    Example:
        Input: "'=0-- "
        Output: "%27%3D0--%20"

    Args:
        value: The string value to URL encode.

    Returns:
        The URL-encoded string.
    """
    if not isinstance(value, str):
        return value

    return quote(value, safe="")


def sanitize_for_json_output(value: str) -> str:
    """
    Sanitize a string value for safe JSON output.

    Removes or escapes characters that could cause issues in JSON
    or be used for injection attacks.

    Args:
        value: The string value to sanitize.

    Returns:
        The sanitized string.
    """
    if not isinstance(value, str):
        return value

    # Remove null bytes
    value = value.replace("\x00", "")

    # Remove or escape other problematic control characters
    # but keep newlines, tabs (they're valid in JSON when escaped)
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", value)

    return value


def sanitize_api_string_value(value: str) -> str:
    """
    Sanitize a string value for API output.

    This applies multiple sanitization steps suitable for API responses:
    - HTML entity encoding for XSS prevention
    - Control character removal

    Args:
        value: The string value to sanitize.

    Returns:
        The sanitized string.
    """
    if not isinstance(value, str):
        return value

    # First remove control characters
    value = sanitize_for_json_output(value)

    # Then HTML encode for XSS prevention
    value = sanitize_for_html(value)

    return value


def sanitize_dict_values(data: dict, fields: set = None) -> dict:
    """
    Sanitize string values in a dictionary.

    Args:
        data: The dictionary containing values to sanitize.
        fields: Optional set of field names to sanitize.
                If None, sanitizes all known user-controlled fields.

    Returns:
        The dictionary with sanitized values.
    """
    if not isinstance(data, dict):
        return data

    fields = fields or OCP_USER_CONTROLLED_FIELDS
    result = data.copy()

    for key, value in result.items():
        if key in fields and isinstance(value, str):
            result[key] = sanitize_api_string_value(value)
        elif isinstance(value, dict):
            result[key] = sanitize_dict_values(value, fields)
        elif isinstance(value, list):
            result[key] = sanitize_list_values(value, fields)

    return result


def sanitize_list_values(data: list, fields: set = None) -> list:
    """
    Sanitize string values in a list.

    Args:
        data: The list containing values to sanitize.
        fields: Optional set of field names to sanitize in nested dicts.

    Returns:
        The list with sanitized values.
    """
    if not isinstance(data, list):
        return data

    fields = fields or OCP_USER_CONTROLLED_FIELDS
    result = []

    for item in data:
        if isinstance(item, dict):
            result.append(sanitize_dict_values(item, fields))
        elif isinstance(item, list):
            result.append(sanitize_list_values(item, fields))
        else:
            result.append(item)

    return result


def prepare_value_for_url_param(value: str, field_name: str = None) -> str:
    """
    Prepare a value for use as a URL parameter.

    This should be used when returning values that will be used
    in URL parameters in the UI, such as project names.

    Args:
        value: The string value to prepare.
        field_name: Optional field name for context.

    Returns:
        The URL-safe string.
    """
    if not isinstance(value, str):
        return value

    # First sanitize for general safety
    value = sanitize_for_json_output(value)

    # Then URL encode
    return sanitize_for_url(value)


def sanitize_api_response(data: Any, url_encode_fields: set = None) -> Any:
    """
    Sanitize an API response data structure.

    This function recursively processes API response data to sanitize
    user-controlled string values. It's designed to be called on
    response data before sending to clients.

    Args:
        data: The API response data (dict, list, or primitive).
        url_encode_fields: Optional set of fields that should be URL encoded.
                          If provided, these fields will be URL encoded
                          instead of just HTML escaped.

    Returns:
        The sanitized response data.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in (url_encode_fields or set()) and isinstance(value, str):
                result[key] = prepare_value_for_url_param(value, key)
            elif key in OCP_USER_CONTROLLED_FIELDS and isinstance(value, str):
                result[key] = sanitize_api_string_value(value)
            elif isinstance(value, (dict, list)):
                result[key] = sanitize_api_response(value, url_encode_fields)
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        return [sanitize_api_response(item, url_encode_fields) for item in data]
    else:
        return data
