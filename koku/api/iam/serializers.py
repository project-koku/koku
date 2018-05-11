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
from django.db import transaction

from rest_framework import serializers

from .model import Customer, User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""
    email = serializers.CharField(required=True,
                                  max_length=150,
                                  allow_null=False)
    class Meta:
        """Metadata for the serializer."""
        model = User
        fields = ('uuid', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True, 'required': True,
                                     'style': {'input_type': 'password'},
                                     'max_length': 128, 'allow_null': False}}


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for the Customer model."""
    owner = UserSerializer()
    class Meta:
        """Metadata for the serializer."""
        model = Customer
        fields = ('uuid', 'name', 'owner', 'date_created')


    @transaction.atomic
    def create(self, validated_data):
        """Create a customer and owner."""
        owner_data = validated_data.pop('owner')
        owner = User.objects.create(**owner_data)

        validated_data['owner_id'] = owner.id
        customer = Customer.objects.create(**validated_data)
        customer.user_set.add(owner)
        customer.save()

        return customer
