from dataclasses import dataclass
from dataclasses import field
from datetime import date
from typing import Any
from typing import Dict
from typing import List

from dateutil.parser import parse
from django.conf import settings

from api.utils import DateHelper


@dataclass
class ManagedSqlMetadata:
    schema: str
    ocp_source_uuids: List[str]
    cloud_provider_uuid: str
    start_date: date
    end_date: date
    matched_tag_strs: List[str]
    days_tup: tuple = field(init=False)
    year: str = field(init=False)
    month: str = field(init=False)

    def __post_init__(self):
        self._check_date_parameters_format()
        if not self.ocp_source_uuids:
            raise ValueError("ocp_source_uuids must not be empty.")
        if len(self.cloud_provider_uuid) == 0:
            raise ValueError("cloud_provider_uuid must not be empty.")
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")
        self._generate_sql_params()

    def _check_date_parameters_format(self):
        """Checks to make sure the date parameters are in the correct format"""
        if type(self.start_date) == str:
            self.start_date = parse(self.start_date).astimezone(tz=settings.UTC)
        if type(self.end_date) == str:
            self.end_date = parse(self.end_date).astimezone(tz=settings.UTC)

    def _generate_sql_params(self):
        """Populates additional SQL parameters options"""
        days = DateHelper().list_days(self.start_date, self.end_date)
        self.days_tup = tuple(str(day.day) for day in days)
        self.year = self.start_date.strftime("%Y")
        self.month = self.start_date.strftime("%m")

    def build_params(self, requested_keys: List[str]) -> Dict[str, Any]:
        """
        Builds and returns a dictionary of parameters based on requested keys.

        Args:
            requested_keys (List[str]): The keys the caller wants in the result.

        Returns:
            Dict[str, Any]: A dictionary containing the requested keys and their values.
        """
        base_params = {
            "schema": self.schema,  # Placeholder if needed
            "start_date": self.start_date,
            "end_date": self.end_date,
            "month": self.month,
            "year": self.year,
            "matched_tag_strs": self.matched_tag_strs,
            "ocp_source_uuids": self.ocp_source_uuids,
            "cloud_provider_uuid": self.cloud_provider_uuid,
            "days_tup": self.days_tup,
            "days": self.days_tup,
        }
        return {key: base_params[key] for key in requested_keys}
