#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from rest_framework import serializers

from api.currency.currencies import CURRENCIES
from api.user_settings.settings import COST_TYPES
from api.utils import get_cost_type
from api.utils import get_currency


class QueryParamSerializer(serializers.Serializer):
    """Serializer for handling query parameters."""

    cost_type = serializers.ChoiceField(choices=COST_TYPES, required=False)
    currency = serializers.ChoiceField(choices=CURRENCIES, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize query param serializer."""
        super().__init__(*args, **kwargs)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        super().validate(data)
        if not data.get("cost_type"):
            data["cost_type"] = get_cost_type(self.context.get("request"))
        if not data.get("currency"):
            data["currency"] = get_currency(self.context.get("request"))
        print(data)
        return data
