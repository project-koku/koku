#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Blueprint util functions."""

from functools import wraps


def add_routes_to_blueprint(blueprint, routes):
    """Assign url route function configuration to given blueprint."""
    for mod_routes in routes.values():
        for route in mod_routes:
            blueprint.add_url_rule(
                route['rule'],
                endpoint=route.get('endpoint', None),
                view_func=route['view_func'],
                **route.get('options', {}))


def application_route(rule, routes, **kwargs):
    """Decorate function to mark a generic application route."""
    def wrapper(funcion):  # pylint: disable=missing-docstring
        if funcion.__module__ not in routes.keys():
            routes[funcion.__module__] = []

        routes[funcion.__module__].append(dict(
            rule=rule,
            view_func=funcion,
            options=kwargs,
        ))

        @wraps(funcion)
        def wrapped(*args, **kwargs):  # pylint: disable=missing-docstring
            return funcion(*args, **kwargs)
        return wrapped
    return wrapper
