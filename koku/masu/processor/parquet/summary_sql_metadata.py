import pkgutil
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
class SummarySqlMetadata:
    schema: str
    cloud_provider_uuid: str
    start_date: date
    end_date: date
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        self.initialize_parameters()
        if self.end_date is None:
            self.end_date = DateHelper().today.strftime("%Y-%m-%d")
        if len(self.cloud_provider_uuid) == 0:
            raise ValueError("cloud_provider_uuid must not be empty.")
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")

    def initialize_parameters(self):
        self.parameters = {k: v for k, v in self.__dict__.items() if k != "parameters"}
        if type(self.start_date) == str:
            self.start_date = parse(self.start_date).astimezone(tz=settings.UTC)
            self.add_parameter("start_date", self.start_date)
        if type(self.end_date) == str:
            self.end_date = parse(self.end_date).astimezone(tz=settings.UTC)
            self.add_parameter("end_date", self.end_date)

        days = DateHelper().list_days(self.start_date, self.end_date)
        self.add_parameter("days_tup", tuple(str(day.day) for day in days))
        self.add_parameter("year", self.start_date.strftime("%Y"))
        self.add_parameter("month", self.start_date.strftime("%m"))

    def add_parameter(self, key, value):
        self.parameters[key] = value

    def build_params(self, requested_keys: List[str]) -> Dict[str, Any]:
        """
        Builds and returns a dictionary of parameters based on requested keys.

        Args:
            requested_keys (List[str]): The keys the caller wants in the result.

        Returns:
            Dict[str, Any]: A dictionary containing the requested keys and their values.
        """
        return {key: self.parameters.get(key) for key in requested_keys}

    def prepare_template(self, filepath):
        """
        Prepares the template & gathers params for execution
        """
        sql_file = pkgutil.get_data("masu.database", filepath)
        sql_file_decoded = sql_file.decode("utf-8")
        return sql_file_decoded, self.parameters

    def remove_duplicates(self):
        """
        Stop gap solution to for preventing duplicates in the args & kwargs
        during celery calls at the moment.
        """
        # TODO: I can't pass all parameters in due
        # to there being duplicates between the args
        # kwargs such as: start_date, end_date,
        self.parameters.pop("start_date")
        self.parameters.pop("end_date")
        self.parameters.pop("days_tup")

    def restore_parameters(self, dict):
        for key, value in dict.items():
            if key not in self.parameters:
                self.parameters[key] = value
