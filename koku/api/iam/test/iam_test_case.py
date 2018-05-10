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
"""Test Case extension to collect common test data"""

from django.test import TestCase

class IamTestCase(TestCase):
    '''Abstract Class for sharing test data'''
    def setUp(self):
        self.user_data = [{'username': 'testy',
                           'password': '12345',
                           'first_name': 'Testy',
                           'last_name': 'McTesterson',
                           'email': 'test@test.foo'},
                          {'username': 'foo',
                           'password': 's3kr1t',
                           'first_name': 'Foo',
                           'last_name': 'Bar',
                           'email': 'foo@foo.bar'}]

        self.customer_data = [{'name' : 'test_customer_1'},
                              {'name' : 'test_customer_2'}]

