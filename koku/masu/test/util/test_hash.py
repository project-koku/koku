#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the hash util."""
import hashlib
import random
import string
from unittest.mock import patch

from masu.exceptions import HasherError
from masu.test import MasuTestCase
from masu.util.hash import Hasher


class HasherUtilTests(MasuTestCase):
    """Test the hashing utility class."""

    def setUp(self):
        """Shared variables for hasher tests."""
        super().setUp()
        self.encoding = "utf-8"
        self.hash_function = random.choice(list(hashlib.algorithms_guaranteed))
        if "shake" in self.hash_function:
            self.hasher = Hasher(
                hash_function=self.hash_function, length=random.randint(8, 64), encoding=self.encoding
            )
        else:
            self.hasher = Hasher(hash_function=self.hash_function, encoding=self.encoding)
        self.string_to_hash = "".join([random.choice(string.ascii_letters) for _ in range(16)])

    def test_initializer(self):
        """Test that the proper variables are initialized."""
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
        hash_function = "shake_128"
        with self.assertRaises(HasherError):
            Hasher(hash_function=hash_function)

        Hasher(hash_function=hash_function, length=16)

    def test_unsupported_algorithm(self):
        """Test that an exception is raised for unsupported algorithms."""
        bad_algorithm = "zuul"

        with self.assertRaises(HasherError):
            Hasher(hash_function=bad_algorithm)

    @patch("masu.util.hash.hashlib", spec=hashlib)
    def test_guaranteed_algorithms(self, mock_hashlib):
        """Test that an exception is raised for a guaranteed algorithm."""
        bad_algorithm = "test_hash_function"
        mock_hashlib.algorithms_guaranteed = [bad_algorithm]
        mock_hashlib.test_hash_function = None

        with self.assertRaises(HasherError):
            Hasher(hash_function=bad_algorithm)
