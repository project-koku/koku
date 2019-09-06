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

"""Serializer to capture server status."""

from rest_framework import serializers


class SourcesSerializer(serializers.Serializer):
    """Serializer for the Status model."""

    api_version = serializers.IntegerField()
    commit = serializers.CharField()
    modules = serializers.DictField()
    platform_info = serializers.DictField()
    python_version = serializers.CharField()
    rbac_cache_ttl = serializers.CharField()
