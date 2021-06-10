#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""IBM utility functions and vars."""
import hashlib
import logging

LOG = logging.getLogger(__name__)


def generate_etag(param):
    """Generate etag for IBM Cloud report."""
    return hashlib.md5(str(param).encode()).hexdigest()


def generate_assembly_id(params):
    """Generate assembly id for IBM Cloud report."""
    return ":".join([str(param) for param in params if param])
