#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tags module."""

from .all.openshift.queries import OCPAllTagQueryHandler
from .aws.openshift.queries import OCPAWSTagQueryHandler
from .aws.queries import AWSTagQueryHandler
from .azure.openshift.queries import OCPAzureTagQueryHandler
from .azure.queries import AzureTagQueryHandler
from .oci.queries import OCITagQueryHandler
from .ocp.queries import OCPTagQueryHandler
