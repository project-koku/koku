#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""VM count dataclass"""
from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel
from pydantic import model_validator
from pydantic import ValidationError

from api.metrics import constants as metric_constants
from api.utils import DateHelper as dh


class VMParams(BaseModel):
    """Data class to manage parameters for VM count queries."""

    schema: str
    start_date: date
    end_date: date
    source_uuid: UUID
    report_period_id: int

    @model_validator(mode="after")
    def validate_start_and_end(self) -> Self:
        if self.start_date > self.end_date:
            raise ValidationError("start_date cannot be after end_date")
        return self

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

    def build_parameters(self, context_params):
        """Combines base parameters with context-specific parameters.

        Args:
            context_params (dict): A dictionary of context-specific parameters.

        Returns:
            (Dict): A dictionary containing the combined base and context parameters.
        """
        base_params = self._create_base_parameters()
        base_params.update(context_params)
        return base_params

    def build_tag_based_rate_parameters(self, tag_based_price_list, metric_name):
        """Builds the SQL query and parameters for tag-based VM rates.

        Returns:
            (Tuple[str, list[Dict]]): A tuple containing the SQL query and a list of tag-based parameters.
                Returns empty list if no tag rates are found.
        """

        tag_rates = tag_based_price_list.get(metric_name, {}).get("tag_rates", None)
        if not tag_rates:
            return
        tag_parameters = []
        for rate_type, rate_list in tag_rates.items():
            for tag_rate in rate_list:
                tag_based_params = {"rate_type": rate_type, "tag_key": tag_rate.get("tag_key")}
                if metric_name in [metric_constants.OCP_VM_MONTH, metric_constants.OCP_VM_CORE_MONTH]:
                    tag_based_params["amortized_denominator"] = dh().days_in_month(self.start_date)
                    tag_based_params["cost_type"] = "Tag"
                if default_rate := tag_rate.get("tag_key_default", None):
                    tag_based_params["default_rate"] = default_rate
                if value_rates := {
                    key_value: rate_dict.get("value")
                    for key_value, rate_dict in tag_rate.get("tag_values", {}).items()
                    if rate_dict.get("value") != tag_based_params.get("default_rate", {})
                }:
                    tag_based_params["value_rates"] = value_rates
                tag_parameters.append(self.build_parameters(tag_based_params))
        return tag_parameters
