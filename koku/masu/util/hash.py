#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Hashing utility."""
import hashlib

from masu.exceptions import HasherError


class Hasher:
    """A utility class to create hashes."""

    def __init__(self, hash_function, length=None, encoding="utf-8"):
        """Initialize the Hasher.

        Args:
            hash_function (str): String representation of hash function
                Ex. 'md5'
            length (int): The digest length for SHAKE algorithms
            encoding (str): Encoding used to convert string to bytes

        Returns:
            (Hasher): the initialized Hasher

        """
        self.length = length
        self.hash_function = hash_function
        self.encoding = encoding

    def get_hash_function(self):
        """Get the hash function."""
        return self._hash_function

    def set_hash_function(self, hash_function):
        """Set the hash function used.

        Args:
            hash_function (str): String representation of hash function
                Ex. 'md5'

        Returns:
            (hashlib hash function)

        """
        if "shake" in hash_function and not self.length:
            errmsg = f"{hash_function} requires length to be set"
            raise HasherError(errmsg)

        self._hash_function = getattr(hashlib, hash_function, None)

        if not self._hash_function:
            errmsg = f"{hash_function} is not currently supported."
            if hash_function in hashlib.algorithms_guaranteed:
                errmsg = f"{hash_function} needs Hasher implementation."
            raise HasherError(errmsg)

    def hash_string_to_hex(self, string):
        """Return a hex digest of the hashed string.

        Args:
            string (str): The string to be hashed

        Returns:
            (str): The hex string of the hash

        """
        if self.length:
            return self.hash_function(string.encode(self.encoding)).hexdigest(self.length)

        return self.hash_function(string.encode(self.encoding)).hexdigest()

    hash_function = property(get_hash_function, set_hash_function)
