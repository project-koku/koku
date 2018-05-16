#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""API application configuration module."""

import logging

from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError

from koku.env import ENVIRONMENT

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class ApiConfig(AppConfig):
    """API application configuration."""

    name = 'api'

    def ready(self):
        """Determine if app is ready on application startup."""
        try:
            self.startup_status()
            self.check_and_create_service_admin()
        except (OperationalError, ProgrammingError) as op_error:
            if 'no such table' in str(op_error) or \
                    'does not exist' in str(op_error):
                # skip this if we haven't created tables yet.
                return
            else:
                logger.error('Error: %s.', op_error)

    def startup_status(self):  # pylint: disable=R0201
        """Log the status of the server at startup."""
        # noqa: E402 pylint: disable=C0413
        from api.status.models import Status
        status_info = None
        status_count = Status.objects.count()
        if status_count == 0:
            status_info = Status.objects.create()
            status_info.save()
        else:
            status_info = Status.objects.first()

        status_info.startup()

    def create_service_admin(self, service_email):  # pylint: disable=R0201
        """Create the Service Admin."""
        # noqa: E402 pylint: disable=C0413
        from django.contrib.auth.models import User
        service_user = ENVIRONMENT.get_value('SERVICE_ADMIN_USER',
                                             default='admin')
        service_pass = ENVIRONMENT.get_value('SERVICE_ADMIN_PASSWORD',
                                             default='pass')

        User.objects.create_superuser(service_user,
                                      service_email,
                                      service_pass)
        logger.info('Created Service Admin: %s.', service_email)

    def check_and_create_service_admin(self):  # pylint: disable=R0201
        """Check for the service admin and create it if necessary."""
        # noqa: E402 pylint: disable=C0413
        from django.contrib.auth.models import User
        service_email = ENVIRONMENT.get_value('SERVICE_ADMIN_EMAIL',
                                              default='admin@example.com')
        admin_not_present = User.objects.filter(
            email=service_email).count() == 0
        if admin_not_present:
            self.create_service_admin(service_email)
        else:
            logger.info('Service Admin: %s.', service_email)
