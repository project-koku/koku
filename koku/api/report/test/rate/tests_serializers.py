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
"""Test the Rate serializers."""

import random
from decimal import Decimal

import faker
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.rate.serializers import RateSerializer
from reporting.rate.models import TIMEUNITS

class RateSerializerTest(IamTestCase):
    """Rate serializer tests."""

    fake = faker.Faker()

    def setUp(self):
        super().setUp()
        self.fake_data = {'name': self.fake.word(),
                          'description' : self.fake.text(),
                          'price': round(Decimal(random.random()), 6),
                          'timeunit': random.choice(TIMEUNITS)[0],
                          'metric': self.fake.word()}

    def test_create_rate(self):
        """Test creating a rate."""
        with tenant_context(self.tenant):
            instance = None
            serializer = RateSerializer(data=self.fake_data)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertIsNotNone(instance)
            for key, value in self.fake_data.items():
                self.assertTrue(hasattr(instance, key))
                self.assertEqual(self.fake_data.get(key), getattr(instance, key))
