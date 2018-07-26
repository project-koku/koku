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
from django.template.loader import render_to_string

from koku.env import ENVIRONMENT

SUBJECT = 'Welcome to Hybrid Cloud Cost Management'
SENDER = ENVIRONMENT.get_value('EMAIL_SENDER',
                               default='noreply@project-koku.com')
APP_DOMAIN = ENVIRONMENT.get_value('APP_DOMAIN',
                                   default='project-koku.com')
APP_NAMESPACE = ENVIRONMENT.get_value('APP_NAMESPACE',
                                      default='')
if not APP_NAMESPACE == '':
    APP_NAMESPACE = '-' + APP_NAMESPACE
DEFAULT_LOGIN = f'http://koku-ui{APP_NAMESPACE}.{APP_DOMAIN}'
LOGIN_LINK = ENVIRONMENT.get_value('LOGIN_LINK',
                                   default=DEFAULT_LOGIN)


def new_user_login_email(username, email, uuid, token):
    """Send an email with a login link for new users."""
    msg_params = {'username': username, 'login_link': LOGIN_LINK}
    msg_plain = render_to_string('welcome.txt', msg_params)
    msg_html = render_to_string('welcome.html', msg_params)
    send_mail(SUBJECT, msg_plain, SENDER, [email], html_message=msg_html)
