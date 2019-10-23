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

"""TestCase for Attribute Model"""
from django.test import TestCase
from attribute.models import Attribute

class AttributeTest(TestCase):
    def create_attribute(self, \
        name="TEST_AWS_ACCOUNT_ID", \
        value="TEST_12345678910", \
        description="TEST Cost Management's AWS Account ID"):
            return Attribute.objects.create(name=name, value=value, description=description)
    def test_attribute_creation(self):
        attribute = self.create_attribute()
        self.assertTrue(isinstance(attribute, Attribute))
        self.assertEqual(attribute.name, 'TEST_AWS_ACCOUNT_ID')
        self.assertEqual(attribute.value, "TEST_12345678910")
        self.assertEqual(attribute.description, "TEST Cost Management's AWS Account ID")