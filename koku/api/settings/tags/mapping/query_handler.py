#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
from api.settings.tags.mapping.models import Relationship
from api.settings.tags.mapping.models import TagKey


def format_tag_mapping_relationship(data: list[dict[str, dict[str, str]]]) -> list[Relationship]:
    parent_dict = {}

    for item in data:
        parent_data = item["parent"]
        child_data = item["child"]
        parent_uuid = parent_data["uuid"]
        if parent_uuid not in parent_dict:
            parent_dict[parent_uuid] = Relationship(TagKey(**parent_data), TagKey(**child_data))
        else:
            parent_dict[parent_uuid].children.append(TagKey(**child_data))

    formatted_data = list(parent_dict.values())

    return formatted_data
