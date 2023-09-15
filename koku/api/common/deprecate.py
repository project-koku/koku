import functools


def deprecate_url(func):
    @functools.wraps(func)
    def wrapper_deprecate(*args, **kwargs):
        # TODO: Grab header and add deprecation
        pass

    return wrapper_deprecate
