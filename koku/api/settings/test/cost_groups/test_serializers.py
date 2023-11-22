from django.test import TestCase

from api.settings.cost_groups.serializers import CostGroupExcludeSerializer
from api.settings.cost_groups.serializers import CostGroupFilterSerializer
from api.settings.cost_groups.serializers import CostGroupOrderSerializer


class CostGroupFilterSerializerTest(TestCase):
    def test_valid_serializer_data(self):
        data = {"project_name": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupFilterSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_serializer_data(self):
        data = {"bad_field": "example_project"}  # Missing 'default' field
        serializer = CostGroupFilterSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_serialization(self):
        instance_data = {"project_name": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupFilterSerializer(instance_data)
        self.assertEqual(serializer.data, instance_data)


class CostGroupExcludeSerializerTest(TestCase):
    def test_valid_serializer_data(self):
        data = {"project_name": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupExcludeSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_serializer_data(self):
        data = {"bad_field": "example_project", "group": "example_group"}  # Missing 'default' field
        serializer = CostGroupExcludeSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_serialization(self):
        instance_data = {"project_name": "example_project", "group": "example_group", "default": True}
        serializer = CostGroupExcludeSerializer(instance_data)
        self.assertEqual(serializer.data, instance_data)


class CostGroupOrderSerializerTest(TestCase):
    def test_valid_serializer_data(self):
        data = {"project_name": "asc", "group": "desc", "default": "asc"}
        serializer = CostGroupOrderSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_serializer_data(self):
        data = {"project_name": "example_project", "group": "example_group"}  # Invalid choices
        serializer = CostGroupOrderSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_serialization(self):
        instance_data = {"project_name": "asc", "group": "desc", "default": "asc"}
        serializer = CostGroupOrderSerializer(instance_data)
        self.assertEqual(serializer.data, instance_data)
