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

"""Test the blueprint util functions."""

import random
import string
from datetime import datetime, timedelta

from flask import Blueprint
import faker
from unittest.mock import call, patch, Mock

from masu.util.blueprint import add_routes_to_blueprint, application_route

from tests import MasuTestCase

class BlueprintUtilTests(MasuTestCase):

    def setUp(self):
        super().setUp()
        self.blueprint = Blueprint('test', __name__, url_prefix='/test')
        self.routes = {}
        self.rule = '/endpoint/'
        self.expected_keys = ['rule', 'view_func', 'options']
        self.route_name = 'test.test_endpoint'

        @application_route(self.rule, self.routes)
        def test_endpoint():
            return 'Test'

    def test_application_route(self):
        """Test that the endpoint function is added to the routes dict."""
        self.assertNotEqual(self.routes, {})
        self.assertIn(__name__, self.routes)
        route_keys = list(self.routes.get(__name__)[0].keys())
        self.assertEqual(route_keys,
                         self.expected_keys)

    def test_add_routes_to_blueprint(self):
        """Test that a routes dict is added to a blueprint."""
        self.assertNotIn(self.route_name, self.app.view_functions)
        self.assertEqual(len(self.blueprint.deferred_functions), 0)
        add_routes_to_blueprint(self.blueprint, self.routes)
        self.assertEqual(len(self.blueprint.deferred_functions), 1)
        self.app.register_blueprint(self.blueprint)
        self.assertIn(self.route_name, self.app.view_functions)
