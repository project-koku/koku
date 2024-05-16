#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for AWS Resources/EC2 Compute Reports."""
from api.report.provider_map import ProviderMap

CSV_FIELD_MAP = {"account": "id", "account_alias": "alias"}


class AWSEC2ComputeProviderMap(ProviderMap):
    """AWS EC2 Compute Provider Map."""

    pass
