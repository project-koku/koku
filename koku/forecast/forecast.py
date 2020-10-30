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
"""Base forecasting module."""
from datetime import datetime
from datetime import timedelta

from api.models import Provider


class Forecast:
    """Base forecasting class."""

    def __init__(self, query_params):
        """Class Constructor."""
        pass

    def predict(self):
        """Execute forecast and return prediction."""
        now = datetime.now()
        response = [
            {
                "date": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
                "value": 1,
                "confidence90_max": 2,
                "confidence90_min": 0,
            },
            {
                "date": (now + timedelta(days=2)).strftime("%Y-%m-%d"),
                "value": 2,
                "confidence90_max": 3,
                "confidence90_min": 1,
            },
            {
                "date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
                "value": 3,
                "confidence90_max": 4,
                "confidence90_min": 2,
            },
            {
                "date": (now + timedelta(days=4)).strftime("%Y-%m-%d"),
                "value": 4,
                "confidence90_max": 5,
                "confidence90_min": 3,
            },
            {
                "date": (now + timedelta(days=5)).strftime("%Y-%m-%d"),
                "value": 5,
                "confidence90_max": 6,
                "confidence90_min": 4,
            },
        ]
        return response


class AWSForecast(Forecast):
    """Azure forecasting class."""

    provider = Provider.PROVIDER_AWS


class AzureForecast(Forecast):
    """Azure forecasting class."""

    provider = Provider.PROVIDER_AZURE


class OCPForecast(Forecast):
    """OCP forecasting class."""

    provider = Provider.PROVIDER_OCP


class OCPAWSForecast(Forecast):
    """OCP+AWS forecasting class."""

    provider = Provider.OCP_AWS


class OCPAzureForecast(Forecast):
    """OCP+Azure forecasting class."""

    provider = Provider.OCP_AZURE


class OCPAllForecast(Forecast):
    """OCP+All forecasting class."""

    provider = Provider.OCP_ALL
