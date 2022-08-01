#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Custom Koku Dev Middleware."""
import json
import logging
from base64 import b64decode
from base64 import b64encode
from unittest.mock import Mock

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from api.common import RH_IDENTITY_HEADER
from api.iam.models import User

LOG = logging.getLogger(__name__)


class DevelopmentIdentityHeaderMiddleware(MiddlewareMixin):
    """Middleware to add 3scale header for development."""

    header = RH_IDENTITY_HEADER

    def process_request(self, request):
        """Inject an identity header for development purposes.
        Note: This identity object is still processed by koku.middleware.IdentityHeaderMiddleware
        Args:
            request (object): The request object
        Example object:
            request.user = {
                "identity": {
                    "account_number": "10001",
                    "type": "User",
                    "user": {
                        "username": "user_dev",
                        "email": "user_dev@foo.com",
                        "is_org_admin": False
                        "access": {
                            "aws.account": {
                                "read": ["1234567890AB", "234567890AB1"]
                            }
                            "azure.subscription_guid": {
                                "read": ["*"]
                            }
                        }
                    },
                },
                "entitlements": {"cost_management": {"is_entitled": True}},
            }
        """
        if hasattr(request, "META") and (hasattr(settings, "DEVELOPMENT_IDENTITY") and settings.DEVELOPMENT_IDENTITY):
            request_id_header = None
            if request.META.get(self.header):
                request_id_header = json.loads(b64decode(request.META.get(self.header)).decode("utf-8"))
            identity_header = request_id_header or settings.DEVELOPMENT_IDENTITY

            if hasattr(settings, "FORCE_HEADER_OVERRIDE") and settings.FORCE_HEADER_OVERRIDE:
                identity_header = settings.DEVELOPMENT_IDENTITY

            user_dict = identity_header.get("identity", {}).get("user")
            user = Mock(
                spec=User,
                access=user_dict.get("access", {}),
                username=user_dict.get("username", "user_dev"),
                email=user_dict.get("email", "user_dev@foo.com"),
                admin=user_dict.get("is_org_admin", False),
                customer=Mock(
                    account_id=identity_header.get("account_number", "10001"),
                    org_id=identity_header.get("org_id", "1234567"),
                    schema_name=f'org{identity_header.get("org_id", "1234567")}',
                ),
                req_id="DEVELOPMENT",
            )

            request.user = user
            json_identity = json.dumps(identity_header)
            LOG.info("Identity: %s", json_identity)
            dev_header = b64encode(json_identity.encode("utf-8")).decode("utf-8")
            request.META[self.header] = dev_header
