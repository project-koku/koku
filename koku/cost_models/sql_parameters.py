#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""VM count dataclass"""
from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class BaseCostModelParams(BaseModel):
    """Data class to manage parameters for VM count queries."""

    schema_name: str = Field(serialization_alias="schema")
    start_date: date
    end_date: date
    source_uuid: UUID
    report_period_id: int

    @model_validator(mode="after")
    def validate_start_and_end(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")
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
            "schema": self.schema_name,
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
