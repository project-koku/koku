from django.db import models

class Attribute(models.Model):
    name = models.CharField(max_length=255, help_text='The name of the attribute')
    value = models.TextField(null=True)
    description = models.TextField(null=True)
    updated_timestamp = models.DateTimeField(auto_now=True, blank=True, null=True)
    created_timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)
