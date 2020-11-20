#
# Copyright 2020 Red Hat, Inc.
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
"""GCP utility functions and vars."""

GCP_SERVICE_LINE_ITEM_TYPE_MAP = {
    "Compute Engine": "usage",
    "Kubernetes Engine": "usage",
    "Cloud Functions": "usage",
    "Clould Run": "usage",
    "VMware Engine": "usage",
    "Filestore": "storage",
    "Storage": "storage",
    "Data Transfer": "storage",
    "VPC network": "network",
    "Network services": "network",
    "Hybrid Connectivity": "network",
    "Network Service Tiers": "network",
    "Network Security": "network",
    "Network Intelligence": "network",
    "Bigtable": "database",
    "Datastore": "database",
    "Database Migrations": "database",
    "Firestore": "database",
    "MemoryStore": "database",
    "Spanner": "database",
    "SQL": "database",
}
