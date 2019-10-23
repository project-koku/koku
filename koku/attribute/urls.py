from rest_framework.routers import DefaultRouter
from .views import AttributeViewSet
# from django.urls import include, path
from django.conf.urls import include, url

ROUTER = DefaultRouter()
# ROUTER.register(r'attribute_url', AttributeViewSet, base_name='attribute_base_name')

# urlpatterns = [
#     path('', AttributeViewSet.as_view({'get': 'list'}), name='attribute_url_name')
# ]
ROUTER.register(r'attributes', AttributeViewSet, base_name='attributes')
# pylint: disable=invalid-name
urlpatterns = [
    url(r'^', include(ROUTER.urls)),
]