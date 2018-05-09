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

"""Identity and Access Serializers."""
# disabled module-wide due to meta-programming
# pylint: disable=too-few-public-methods

from rest_framework import serializers

from .model import Customer, User

class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for the Customer model."""

    class Meta:
        """Metadata for the serializer."""
        model = Customer
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""

    class Meta:
        """Metadata for the serializer."""
        model = User
        fields = '__all__'
