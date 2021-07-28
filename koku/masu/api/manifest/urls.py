from django.conf.urls import include
from django.urls import path
from manifest.views import ManifestViewSet
from rest_framework.routers import DefaultRouter

ROUTER = DefaultRouter()
ROUTER.register(r"manifests", ManifestViewSet, basename="manifests")
urlpatterns = [path("", include(ROUTER.urls))]
