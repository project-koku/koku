#
# Copyright 2019 Red Hat, Inc.
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

"""Koku Test Runner."""
import logging

from django.test.runner import DiscoverRunner
from django.test.utils import setup_databases

from api.models import Tenant

LOG = logging.getLogger(__name__)


class KokuTestRunner(DiscoverRunner):
    """Koku Test Runner for Unit Tests."""

    account = '10001'
    schema = f'acct{account}'

    def setup_databases(self, **kwargs):
        """Set up database tenant schema."""
        main_db = setup_databases(
            self.verbosity, self.interactive, self.keepdb, self.debug_sql,
            self.parallel, **kwargs
        )

        tenant = Tenant.objects.get_or_create(schema_name=KokuTestRunner.schema)[0]
        tenant.save()

        return main_db
