from rest_framework import viewsets
from .models import Attribute
from .serializers import AttributeSerializer

from rest_framework.permissions import AllowAny


class AttributeViewSet(viewsets.ModelViewSet):
    queryset = Attribute.objects.all()
    serializer_class = AttributeSerializer
    permission_classes = (AllowAny,)