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

"""Utility for emailing users on creation and password reset."""
from django.core.mail import send_mail

from koku.env import ENVIRONMENT

SUBJECT = 'Welcome to Hybrid Cost Management'
SENDER = ENVIRONMENT.get_value('EMAIL_SENDER',
                               default='noreply@project-koku.com')
BODY = 'Welcome to Hybrid Cost Management.' \
    ' Start gaining insights on your costs today.' \
    ' You user has been created with username {username}.' \
    ' Point your browser to the following URL to reset your password' \
    ' and begin using the service. {reset_link}'
DEFAULT_RESET = 'https://koku-ui.project-koku.com/password-reset.html'
RESET_LINK = ENVIRONMENT.get_value('PASSWORD_RESET_LINK',
                                   default=DEFAULT_RESET)


def new_user_reset_email(username, email, uuid, token):
    """Send an email with a password reset link for new users."""
    reset_link = RESET_LINK + '?uuid=' + uuid + '&token=' + token
    body = BODY.format(username=username, reset_link=reset_link)
    send_mail(SUBJECT, body, SENDER, [email])
