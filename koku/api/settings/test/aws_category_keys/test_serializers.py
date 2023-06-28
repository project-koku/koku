#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test AWS Category Serializer."""
from rest_framework.serializers import ValidationError

from api.settings.aws_category_keys.serializers import SettingsAWSCategoryKeyIDSerializer
from api.settings.aws_category_keys.serializers import SettingsAWSCategoryKeySerializer
from api.settings.test.aws_category_keys.utils import TestAwsCategoryClass


class SettingsAWSCategoryKeySerializerTest(TestAwsCategoryClass):
    """Tests for the AWS category serializer serializer."""

    def test_params_invalid_fields(self):
        """Test parse of exclude params for invalid fields."""
        exclude_params = {"invalid": "param"}
        serializer = SettingsAWSCategoryKeySerializer(data=exclude_params)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_params_valid_fields(self):
        """Test valid fields."""
        param = {"uuid": str(self.uuid), "key": self.key, "enabled": self.enabled}
        serializer = SettingsAWSCategoryKeySerializer(data=param, context=self.request_context)
        self.assertTrue(serializer.is_valid())


class SettingsAWSCategoryKeyIDSerializerTest(TestAwsCategoryClass):
    """Test case for the id serializer."""

    def test_params_invalid_fields(self):
        """Test parse of exclude params for invalid fields."""
        bad_param = {"invalid": "param"}
        serializer = SettingsAWSCategoryKeyIDSerializer(data=bad_param)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_params_valid_fields(self):
        """Test valid fields."""
        param = {"id_list": [self.uuid]}
        serializer = SettingsAWSCategoryKeyIDSerializer(data=param, context=self.request_context)
        self.assertTrue(serializer.is_valid())
