import pkgutil
from dataclasses import dataclass
from datetime import date

from dateutil.parser import parse
from django.conf import settings


@dataclass
class VMCountParams:
    """Data class to manage parameters for VM count queries."""

    schema: str
    start_date: date
    end_date: date
    source_uuid: str
    report_period_id: int

    def __post_init__(self):
        """Performs post-initialization validation and parameter generation.

        Validates date parameters and raises an error if start_date is after end_date.

        Raises:
            ValueError: If start_date is after end_date.
        """
        self._check_date_parameters_format()
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")

    def _check_date_parameters_format(self):
        """Checks to make sure the date parameters are in the correct format"""
        if type(self.start_date) == str:
            self.start_date = parse(self.start_date).astimezone(tz=settings.UTC)
        if type(self.end_date) == str:
            self.end_date = parse(self.end_date).astimezone(tz=settings.UTC)

    def _create_base_parameters(self):
        """Creates a dictionary of base SQL parameters.

        Returns:
            (Dict): A dictionary containing base parameters for SQL queries.
        """
        return {
            "start_date": str(self.start_date),
            "end_date": str(self.end_date),
            "year": self.start_date.strftime("%Y"),
            "month": self.start_date.strftime("%m"),
            "schema": self.schema,
            "source_uuid": str(self.source_uuid),
            "report_period_id": self.report_period_id,
        }

    def build_vm_count_hourly_query(self, rate_type, hourly_rate):
        """Builds the SQL query and parameters for hourly VM cost calculation.

        Returns:
            (Tuple[Dict, str]): A tuple containing the SQL parameters and the decoded SQL query.
        """
        sql_params = self._create_base_parameters()
        sql_params["rate_type"] = rate_type
        sql_params["hourly_rate"] = hourly_rate
        sql_file = pkgutil.get_data("masu.database", "trino_sql/openshift/cost_model/hourly_cost_virtual_machine.sql")
        return sql_file.decode("utf-8"), sql_params

    def build_tag_based_rate_query(self, tag_based_price_list, metric_name):
        """Builds the SQL query and parameters for tag-based VM rates.

        Returns:
            (Tuple[str, list[Dict]]): A tuple containing the SQL query and a list of tag-based parameters.
                Returns empty list and None if no tag rates are found.
        """
        tag_rates = tag_based_price_list.get(metric_name, {}).get("tag_rates", None)
        if not tag_rates:
            return None, []
        tag_parameters = []
        for rate_type, rate_list in tag_rates.items():
            for tag_rate in rate_list:
                sql_params = self._create_base_parameters()
                sql_params["rate_type"] = rate_type
                sql_params["tag_key"] = tag_rate.get("tag_key")
                if default_rate := tag_rate.get("tag_key_default", None):
                    sql_params["default_rate"] = default_rate
                if value_rates := {
                    key_value: rate_dict.get("value")
                    for key_value, rate_dict in tag_rate.get("tag_values", {}).items()
                    if rate_dict.get("value") != sql_params.get("default_rate", {})
                }:
                    sql_params["value_rates"] = value_rates
                tag_parameters.append(sql_params)
        sql_file = pkgutil.get_data("masu.database", "trino_sql/openshift/cost_model/hourly_cost_vm_tag_based.sql")
        return sql_file.decode("utf-8"), tag_parameters
