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
"""Django email settings."""

from .env import ENVIRONMENT

EMAIL_HOST = ENVIRONMENT.get_value('EMAIL_HOST', default=None)
EMAIL_PORT = int(ENVIRONMENT.get_value('EMAIL_PORT', default=587))
DEFAULT_POSTMASTER = 'postmaster@mg.project-koku.com'
EMAIL_HOST_USER = ENVIRONMENT.get_value('EMAIL_HOST_USER',
                                        default=DEFAULT_POSTMASTER)
EMAIL_HOST_PASSWORD = ENVIRONMENT.get_value('EMAIL_HOST_PASSWORD',
                                            default=None)
EMAIL_USE_TLS = bool(ENVIRONMENT.get_value('EMAIL_USE_TLS', default=True))


def get_email_backend():
    """Determine email backend based on configuration."""
    email_backend = 'django.core.mail.backends.smtp.EmailBackend'
    if not EMAIL_HOST:
        email_backend = 'django.core.mail.backends.console.EmailBackend'
    return email_backend
