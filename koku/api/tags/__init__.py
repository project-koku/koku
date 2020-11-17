#
# Copyright 2019 Red Hat, Inc.
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
"""Tags module."""
from .all.openshift.queries import OCPAllTagQueryHandler  # noqa: F401
from .aws.openshift.queries import OCPAWSTagQueryHandler  # noqa: F401
from .aws.queries import AWSTagQueryHandler  # noqa: F401
from .azure.openshift.queries import OCPAzureTagQueryHandler  # noqa: F401
from .azure.queries import AzureTagQueryHandler  # noqa: F401
from .ocp.queries import OCPTagQueryHandler  # noqa: F401
