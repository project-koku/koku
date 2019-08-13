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

"""Test the hash util."""

import hashlib
import json
import random
import string
from datetime import datetime
from decimal import Decimal

from masu.exceptions import HasherError
from masu.util.hash import Hasher

from masu.test import MasuTestCase


class HasherUtilTests(MasuTestCase):
    """Test the hashing utility class."""

    def setUp(self):
        super().setUp()
        self.encoding = 'utf-8'
        self.hash_function = random.choice(list(hashlib.algorithms_guaranteed))
        # self.hash_function = 'sha3_224'
        if 'shake' in self.hash_function:
            self.hasher = Hasher(
                hash_function=self.hash_function,
                length=random.randint(8, 64),
                encoding=self.encoding,
            )
        else:
            self.hasher = Hasher(
                hash_function=self.hash_function, encoding=self.encoding
            )
        self.string_to_hash = ''.join(
            [random.choice(string.ascii_letters) for _ in range(16)]
        )

    def test_initializer(self):
        """Test that the proper variables are initialized."""
        # encoding = 'ascii'
        # hasher = Hasher(hash_function=self.hash_function, encoding=encoding)
        hash_function = getattr(hashlib, self.hash_function)
        self.assertEqual(self.hasher.hash_function, hash_function)
        self.assertEqual(self.hasher.encoding, self.encoding)

    def test_hash_string_to_hex(self):
        """Test that the string hash function returns a hex string."""
        result = self.hasher.hash_string_to_hex(self.string_to_hash)
        self.assertIsInstance(result, str)
        for char in result:
            self.assertIn(char, string.hexdigits)

    def test_reliable_hash(self):
        """Test that the hasher creates a true hash."""
        result_one = self.hasher.hash_string_to_hex(self.string_to_hash)
        result_two = self.hasher.hash_string_to_hex(self.string_to_hash)

        self.assertEqual(result_one, result_two)

    def test_shake_length_required(self):
        """Test that shake algorithms require a length."""
        hash_function = 'shake_128'
        with self.assertRaises(HasherError):
            hasher = Hasher(hash_function=hash_function)

        hasher = Hasher(hash_function=hash_function, length=16)

    def test_unsupported_algorithm(self):
        bad_algorithm = 'zuul'

        with self.assertRaises(HasherError):
            hasher = Hasher(hash_function=bad_algorithm)
