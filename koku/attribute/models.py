#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Model for Attributes."""
from django.db import models


"""A dictionary of configuration-related key-value pairs."""
class Attribute(models.Model):
    name = models.CharField(max_length=255, help_text='The name of the attribute')
    value = models.TextField(null=True)
    description = models.TextField(null=True)
    updated_timestamp = models.DateTimeField(auto_now=True, blank=True, null=True)
    created_timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)
