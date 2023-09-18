from functools import wraps


def add_deprecation_header(response):
    # https://greenbytes.de/tech/webdav/draft-ietf-httpapi-deprecation-header-latest.html
    response.headers["Deprecation"] = True


def deprecate_view(viewfunc, deprecation_kwargs):
    @wraps(viewfunc)
    def _wrapped_view_func(request, *args, **kw):
        response = viewfunc(request, *args, **kw)
        add_deprecation_header(response)
        return response

    return _wrapped_view_func


# def never_cache(view_func):
#     """
#     Decorator that adds headers to a response so that it will never be cached.
#     """
#     @wraps(view_func)
#     def _wrapped_view_func(request, *args, **kwargs):
#         response = view_func(request, *args, **kwargs)
#         add_never_cache_headers(response)
#         return response
#     return _wrapped_view_func

# def add_never_cache_headers(response):
#     """
#     Add headers to a response to indicate that a page should never be cached.
#     """
#     patch_response_headers(response, cache_timeout=-1)
#     patch_cache_control(response, no_cache=True, no_store=True, must_revalidate=True, private=True)

# def patch_response_headers(response, cache_timeout=None):
#     """
#     Add HTTP caching headers to the given HttpResponse: Expires and
#     Cache-Control.

#     Each header is only added if it isn't already set.

#     cache_timeout is in seconds. The CACHE_MIDDLEWARE_SECONDS setting is used
#     by default.
#     """
#     if cache_timeout is None:
#         cache_timeout = settings.CACHE_MIDDLEWARE_SECONDS
#     if cache_timeout < 0:
#         cache_timeout = 0  # Can't have max-age negative
#     if not response.has_header('Expires'):
#         response.headers['Expires'] = http_date(time.time() + cache_timeout)
#     patch_cache_control(response, max_age=cache_timeout)
