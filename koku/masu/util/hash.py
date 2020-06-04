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

        try:
            self._hash_function = getattr(hashlib, hash_function)
        except AttributeError:
            if hash_function in hashlib.algorithms_guaranteed:
                errmsg = f"{hash_function} needs Hasher implementation."
                raise HasherError(errmsg)
            errmsg = f"{hash_function} is not currently supported."
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
