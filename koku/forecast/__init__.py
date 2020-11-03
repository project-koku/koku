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
"""Forecasting Module."""
from .forecast import AWSForecast  # noqa: F401
from .forecast import AzureForecast  # noqa: F401
from .forecast import Forecast  # noqa: F401
from .forecast import OCPAllForecast  # noqa: F401
from .forecast import OCPAWSForecast  # noqa: F401
from .forecast import OCPAzureForecast  # noqa: F401
from .forecast import OCPForecast  # noqa: F401
