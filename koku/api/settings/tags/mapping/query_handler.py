#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
from rest_framework.response import Response


def format_tag_mapping_relationship(original_response):
    original_data = original_response.data
    parent_dict = {}

    for item in original_data:
        parent_data = item["parent"]
        child_data = item["child"]
        parent_uuid = parent_data["uuid"]
        if parent_uuid not in parent_dict:
            parent_dict[parent_uuid] = parent_data
            parent_dict[parent_uuid]["children"] = [child_data]
        else:
            parent_dict[parent_uuid]["children"].append(child_data)

    formatted_data = [{"parent": parent_data} for parent_data in parent_dict.values()]
    formatted_response = Response(formatted_data)

    return formatted_response
