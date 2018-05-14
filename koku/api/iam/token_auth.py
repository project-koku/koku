#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Generate Authentication Tokens."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token


# pylint: disable=W0613
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    """Create authentication tokens when users are created.

    @api {post} /api/v1/token-auth/
    @apiName getToken
    @apiGroup Authentication
    @apiVersion 1.0.0
    @apiDescription Get an authentication token for a user.

    @apiParam (Request Body) {String} username The user's username
    @apiParam (Request Body) {String} password The user's password
    @apiParamExample {json} Request Body:
        {
            "username": "smithj",
            "password": "str0ng!P@ss"
        }

    @apiSuccess {String} token  The authentication token for the user.
    @apiSuccessExample {json} Success-Response:
        HTTP/1.1 200 OK
        {
            "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
        }
    """
    if created:
        Token.objects.create(user=instance)
