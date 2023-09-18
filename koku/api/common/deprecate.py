from functools import wraps


def deprecate_view(**kwargs):
    def _deprecate_controller(viewfunc):
        @wraps(viewfunc)
        def _deprecate_controlled(request, *args, **kw):
            response = viewfunc(request, *args, **kw)
            return response

        return _deprecate_controlled

    return _deprecate_controller
