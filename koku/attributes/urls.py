from rest_framework import routers
from .views import AttributeViewset
from django.urls import include, path

router = routers.DefaultRouter()
router.register(r'attributes', AttributeViewset)

urlpatterns = [
    path('/', include(router.urls)),
]