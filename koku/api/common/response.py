#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HTTP response utility functions for API views."""


def set_content_length(response, request, renderer_context=None):
    """Set Content-Length header on response to prevent chunked encoding.

    Args:
        response: The DRF Response object
        request: The HTTP request object
        renderer_context: Optional renderer context dict. If not provided,
                         will be extracted from the response if available.

    Returns:
        The response object with Content-Length header set
    """
    # Render the response to get the actual content
    if not response._is_rendered:
        response.accepted_renderer = request.accepted_renderer
        response.accepted_media_type = request.accepted_renderer.media_type
        if renderer_context is not None:
            response.renderer_context = renderer_context
        response.render()
    # Set Content-Length header to force non-chunked encoding
    if hasattr(response, "rendered_content"):
        content_length = len(response.rendered_content)
        response["Content-Length"] = str(content_length)
    return response
