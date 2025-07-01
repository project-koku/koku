import pkgutil
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from decimal import Decimal
from typing import Any

from dateutil.parser import parse
from django.conf import settings

from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.utils import DateHelper
from masu.database.cost_model_db_accessor import CostModelDBAccessor


@dataclass
class SummarySqlMetadata:
    schema: str
    ocp_provider_uuid: str
    cloud_provider_uuid: str
    start_date: date
    end_date: date
    matched_tag_strs: list[str]
    days_tup: tuple = field(init=False)
    year: str = field(init=False)
    month: str = field(init=False)

    def __post_init__(self):
        self._check_date_parameters_format()
        if not self.ocp_provider_uuid:
            raise ValueError("ocp_provider_uuid must not be empty.")
        if len(self.cloud_provider_uuid) == 0:
            raise ValueError("cloud_provider_uuid must not be empty.")
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")
        self._generate_sql_params()

    def _check_date_parameters_format(self):
        """Checks to make sure the date parameters are in the correct format"""
        if isinstance(self.start_date, str):
            self.start_date = parse(self.start_date).astimezone(tz=settings.UTC)
        if isinstance(self.end_date, str):
            self.end_date = parse(self.end_date).astimezone(tz=settings.UTC)

    def _generate_sql_params(self):
        """Populates additional SQL parameters options"""
        days = DateHelper().list_days(self.start_date, self.end_date)
        self.days_tup = tuple(str(day.day) for day in days)
        self.year = self.start_date.strftime("%Y")
        self.month = self.start_date.strftime("%m")

    def build_cost_model_params(self):
        """Set summary parameters based off cost model"""
        cost_model_params = {}
        with CostModelDBAccessor(self.schema, self.cloud_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100
            cost_model_params["markup"] = markup_value or 0

        with CostModelDBAccessor(self.schema, self.ocp_provider_uuid) as cost_model_accessor:
            cost_model_params["distribution"] = cost_model_accessor.distribution_info.get(
                "distribution_type", DEFAULT_DISTRIBUTION_TYPE
            )
        return cost_model_params

    def build_params(self, requested_keys: list[str]) -> dict[str, Any]:
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
            "ocp_provider_uuid": self.ocp_provider_uuid,
            "cloud_provider_uuid": self.cloud_provider_uuid,
            "days_tup": self.days_tup,
            "days": self.days_tup,
        }
        return {key: base_params[key] for key in requested_keys}

    def prepare_template(self, filepath, extra_params={}):
        """
        Prepares the template & gathers params for execution
        """
        base_params = {
            "schema": self.schema,  # Placeholder if needed
            "start_date": self.start_date,
            "end_date": self.end_date,
            "month": self.month,
            "year": self.year,
            "matched_tag_strs": self.matched_tag_strs,
            "ocp_provider_uuid": self.ocp_provider_uuid,
            "cloud_provider_uuid": self.cloud_provider_uuid,
            "days_tup": self.days_tup,
            "days": self.days_tup,
        }
        for key, value in extra_params.items():
            base_params[key] = value

        sql_file = pkgutil.get_data("masu.database", filepath)
        sql_file_decoded = sql_file.decode("utf-8")
        return sql_file_decoded, base_params
