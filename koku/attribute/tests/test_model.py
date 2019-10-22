from django.test import TestCase
from attribute.models import Attribute

class AttributeTest(TestCase):
    def create_attribute(self, \
        name="TEST_AWS_ACCOUNT_ID", \
        value="TEST_12345678910", \
        description="TEST Cost Management's AWS Account ID"):
            return Attribute.objects.create(name=name, value=value, description=description)
    def test_attribute_creation(self):
        attribute = self.create_attribute()
        self.assertTrue(isinstance(attribute, Attribute))
        self.assertEqual(attribute.name, 'TEST_AWS_ACCOUNT_ID')
        self.assertEqual(attribute.value, "TEST_12345678910")
        self.assertEqual(attribute.description, "TEST Cost Management's AWS Account ID")