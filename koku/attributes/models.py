from django.db import models

class Attribute(models.Model):
    name = models.CharField(max_length=255, help_text='The name of the attribute')
    value = models.TextField(null=True)
    description = models.TextField(null=True)
