#!/usr/bin/env python3
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""
Search for the koku SOURCE_REPOSITORY_REF setting in the
e2e-deploy buildfactory dir koku.yaml file.
"""
import logging
import os
import re
import sys


logging.basicConfig(level=logging.INFO, stream=sys.stderr)
LOG = logging.getLogger("update_e2e_srr")


# This regex will search the yaml text for the following pattern:
#
# name: SOURCE_REPOSITORY_REF
# required: false
# value: XXXX
#
# To be able to replace XXXX with the correct ref
# reading the yaml and dumping the updated yaml was not used
# so that the whole file would not be reordered
REGEX = "^(.*?name: SOURCE_REPOSITORY_REF.*?" + os.linesep + ".*?required: .*?" + os.linesep + ".*?value: )(.+?)$"
SRR = re.compile(REGEX, flags=re.MULTILINE)


def set_srr(yaml_file_name, git_ref):
    # This is to ensure that the replacement has no issues since part of the grouping is multiline
    def repl(match):
        return f"{match.group(1)}{git_ref}"

    target_file = os.path.join(os.environ["E2E_REPO"], "buildfactory", yaml_file_name)
    LOG.info(f'Processing "{target_file}"')
    with open(target_file, "r+") as e2e_yaml:
        buff = e2e_yaml.read()
        e2e_yaml.seek(0)
        e2e_yaml.write(SRR.sub(repl, buff))
        e2e_yaml.flush()
        e2e_yaml.truncate()


if __name__ == "__main__":
    try:
        git_ref = sys.argv[1]
    except Exception:
        raise Exception(f"Usage: {os.path.basename(sys.argv[0])} <git-ref>")

    YAML_FILES = [
        os.path.join("hccm", "koku.yaml"),
        os.path.join("hccm-optional", "celery-flower.yaml"),
        os.path.join("hccm-optional", "rdsexporter.yaml"),
    ]

    for yml_file in YAML_FILES:
        set_srr(yml_file, git_ref)
