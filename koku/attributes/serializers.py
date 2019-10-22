from rest_framework import serializers
from .models import Attribute

class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attribute
        fields = ('name', 'value', 'description')
