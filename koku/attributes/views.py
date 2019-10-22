from django.shortcuts import render, redirect, get_list_or_404
#from django.views.generic import ListView, DetailView
from rest_framework import viewsets
from . import models
from . import serializers
from rest_framework.permissions import AllowAny

#
class AttributeViewset(viewsets.ModelViewSet):
    queryset = models.Attribute.objects.all()
    serializer_class = serializers.AttributeSerializer
    permission_classes = (AllowAny,)
# Home view for attributes. Attributes are displayed in a list
