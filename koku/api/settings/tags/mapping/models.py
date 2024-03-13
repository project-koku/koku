#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Dataclasses model for tag mappings query handler."""
import dataclasses


@dataclasses.dataclass(frozen=True)
class TagKey:
    uuid: str
    key: str
    source_type: str


@dataclasses.dataclass(frozen=True)
class Relationship:
    parent: TagKey
    child: TagKey
    children: list[TagKey] = dataclasses.field(default_factory=list)

    def to_dict(self):
        return {
            "parent": dataclasses.asdict(self.parent),
            "child": dataclasses.asdict(self.child),
            "children": [dataclasses.asdict(child) for child in self.children],
        }
