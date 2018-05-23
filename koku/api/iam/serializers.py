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

import secrets
import string

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.validators import validate_email
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .email import new_user_reset_email
from .models import Customer, ResetToken, User, UserPreference


def gen_temp_password():
    """Generate a temporary password."""
    choices = '!@#$%^&*()_+' + string.digits \
        + string.ascii_uppercase + string.ascii_lowercase

    return ''.join(secrets.choice(choices) for i in range(10))


def create_user(username, email, password):
    """Create a user and associated password reset token."""
    user_pass = None
    if password:
        user_pass = password
    else:
        user_pass = gen_temp_password()

    user = User.objects.create_user(username=username,
                                    email=email,
                                    password=user_pass)
    reset_token = ResetToken(user=user)
    reset_token.save()
    new_user_reset_email(username, email, str(user.uuid),
                         str(reset_token.token))
    return user


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""

    email = serializers.EmailField(required=True,
                                   max_length=150,
                                   allow_blank=False,
                                   validators=[validate_email,
                                               UniqueValidator(queryset=User.objects.all())])

    class Meta:
        """Metadata for the serializer."""

        model = User
        fields = ('uuid', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True, 'required': False,
                                     'style': {'input_type': 'password'},
                                     'max_length': 128, 'allow_null': False}}

    @transaction.atomic
    def create(self, validated_data):
        """Create a user from validated data."""
        user = create_user(
            username=validated_data.get('username'),
            email=validated_data.get('email'),
            password=validated_data.get('password'))

        UserSerializer._create_default_preferences(user)
        return user

    @staticmethod
    def _create_default_preferences(user):
        """Set preference defaults for this user."""
        defaults = [{'currency': settings.KOKU_DEFAULT_CURRENCY},
                    {'timezone': settings.KOKU_DEFAULT_TIMEZONE},
                    {'locale': settings.KOKU_DEFAULT_LOCALE}]

        for pref in defaults:
            data = {'preference': pref,
                    'user': model_to_dict(user),
                    'name': list(pref.keys())[0],
                    'description': _('default preference')}
            serializer = UserPreferenceSerializer(data=data)
            if serializer.is_valid(raise_exception=True):
                serializer.save()


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
        owner = create_user(username=owner_data.get('username'),
                            email=owner_data.get('email'),
                            password=owner_data.get('password'))

        validated_data['owner_id'] = owner.id
        customer = Customer.objects.create(**validated_data)
        customer.user_set.add(owner)
        customer.save()

        return customer

    @staticmethod
    def get_authentication_group_for_customer(customer):
        """Get auth group for given customer."""
        return Group.objects.get(name=customer)

    @staticmethod
    def get_users_for_group(group):
        """Get users that belong to a given authentication group."""
        return group.user_set.all()


class NestedUserSerializer(serializers.ModelSerializer):
    """
    User Serializer for nesting inside other serializers.

    This serializer removes uniqueness validation from the username and email
    fields to work around issues documented here:
    https://medium.com/django-rest-framework/dealing-with-unique-constraints-in-nested-serializers-dade33b831d9
    """

    email = serializers.EmailField(required=True,
                                   max_length=150,
                                   allow_blank=False,
                                   validators=[validate_email])

    class Meta:
        """Metadata for the serializer."""

        model = User
        fields = ('uuid', 'username', 'email')
        extra_kwargs = {'username': {'validators': [UnicodeUsernameValidator()]}}


class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for the UserPreference model."""

    user = NestedUserSerializer(label='User')

    class Meta:
        """Metadata for the serializer."""

        model = UserPreference
        fields = ('uuid', 'name', 'description', 'preference', 'user')

    @transaction.atomic
    def create(self, validated_data):
        """Create a preference."""
        user_data = validated_data.pop('user')
        user = User.objects.get(username=user_data['username'])
        validated_data['user_id'] = user.id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update a preference."""
        user_data = validated_data.pop('user')
        user = User.objects.get(username=user_data['username'])
        validated_data['user_id'] = user.id
        return super().update(instance, validated_data)


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for the Password change."""

    token = serializers.UUIDField(required=True)
    password = serializers.CharField(write_only=True,
                                     required=True,
                                     max_length=128,
                                     allow_null=False,
                                     style={'input_type': 'password'})
