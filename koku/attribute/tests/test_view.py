from django.test import TestCase
from django.urls import reverse
from attribute.views import AttributeViewSet
from rest_framework.test import RequestsClient

class AttributeViewTestCase(TestCase): 

    def test_attribute_view_set(self):
        client = RequestsClient()
        response = client.get(reverse('attributes'))
        self.assertEquals(response.status_code, 200, response.text)
    def testTrue(self):
        self.assertTrue(True, "hello world")