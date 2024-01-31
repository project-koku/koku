from django.test import TestCase
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.settings.cost_groups.serializers import CostGroupExcludeSerializer
from api.settings.cost_groups.serializers import CostGroupFilterSerializer
from api.settings.cost_groups.serializers import CostGroupOrderSerializer
from api.settings.cost_groups.serializers import CostGroupProjectSerializer


class CostGroupFilterSerializerTest(TestCase):
    def test_valid_serializer_data(self):
        data = {"project": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupFilterSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_serializer_data(self):
        data = {"bad_field": "example_project"}  # Missing 'default' field
        serializer = CostGroupFilterSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_serialization(self):
        instance_data = {"project": ["example_project"], "group": ["example_group"], "default": True}
        serializer = CostGroupFilterSerializer(instance_data)
        self.assertEqual(serializer.data, instance_data)


class CostGroupExcludeSerializerTest(TestCase):
    def test_valid_serializer_data(self):
        data = {"project": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupExcludeSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_serializer_data(self):
        data = {"bad_field": "example_project", "group": "example_group"}  # Missing 'default' field
        serializer = CostGroupExcludeSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_serialization(self):
        instance_data = {"project": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupExcludeSerializer(instance_data)
        self.assertEqual(serializer.data, instance_data)


class CostGroupOrderSerializerTest(TestCase):
    def test_valid_serializer_data(self):
        data = {"project": "asc", "group": "desc", "default": "asc"}
        serializer = CostGroupOrderSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_serializer_data(self):
        data = {"project": "example_project", "group": "example_group"}  # Invalid choices
        serializer = CostGroupOrderSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_serialization(self):
        instance_data = {"project": "asc", "group": "desc", "default": "asc"}
        serializer = CostGroupOrderSerializer(instance_data)
        self.assertEqual(serializer.data, instance_data)


class CostGroupProjectSerializerTest(IamTestCase):
    def test_validate_project_invalid(self):
        """Test when project is an invalid value"""
        data = {"project": "invalid_project", "group": "Platform"}
        serializer = CostGroupProjectSerializer(data=data)
        with schema_context(self.schema_name):
            self.assertFalse(serializer.is_valid())
        self.assertIn("project", serializer.errors)

    def test_validate_group_invalid(self):
        data = {"project": "koku", "group": "Fake"}
        serializer = CostGroupProjectSerializer(data=data)
        with schema_context(self.schema_name):
            self.assertFalse(serializer.is_valid())
        self.assertIn("group", serializer.errors)

    def test_valid(self):
        """Test we get a valid when a real project and group provided."""
        data = {"project": "koku", "group": "Platform"}
        serializer = CostGroupProjectSerializer(data=data)
        with schema_context(self.schema_name):
            self.assertTrue(serializer.is_valid())
