#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""


def format_tag_mapping_relationship(relationships):
    formatted_relationships = {}
    for relationship in relationships:
        parent_uuid = relationship["parent"]["uuid"]
        if parent_uuid not in formatted_relationships:
            formatted_relationships[parent_uuid] = {
                "parent": relationship["parent"],
                "children": [relationship["child"]] + relationship["children"],
            }
        else:
            formatted_relationships[parent_uuid]["children"].extend([relationship["child"]] + relationship["children"])

    return list(formatted_relationships.values())
