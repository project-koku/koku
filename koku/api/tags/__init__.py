#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tags module."""
from .all.openshift.queries import OCPAllTagQueryHandler  # noqa: F401
from .aws.openshift.queries import OCPAWSTagQueryHandler  # noqa: F401
from .aws.queries import AWSTagQueryHandler  # noqa: F401
from .azure.openshift.queries import OCPAzureTagQueryHandler  # noqa: F401
from .azure.queries import AzureTagQueryHandler  # noqa: F401
from .ocp.queries import OCPTagQueryHandler  # noqa: F401
