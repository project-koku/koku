from rest_framework import routers
from .views import AttributeViewSet
from django.urls import include, path

router = routers.DefaultRouter()
router.register(r'attributes', AttributeViewSet)

urlpatterns = [
    path('/', include(router.urls)),
]