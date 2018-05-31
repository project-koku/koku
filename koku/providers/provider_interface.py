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
"""Provider interface to be used by Koku."""

from abc import ABC, abstractmethod


class ProviderInterface(ABC):
    """Koku interface definition to access backend provider services."""

    @abstractmethod
    def name(self):
        """Get the provider's name."""
        pass

    @abstractmethod
    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that a backend usage source is configured and reachable."""
        pass
