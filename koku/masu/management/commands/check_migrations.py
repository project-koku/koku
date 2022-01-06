#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from django.core.management.base import BaseCommand

from koku.database import check_migrations

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check if migrations need to be run"

    def handle(self, *args, **options):
        """Run our database check_migratons function."""

        self.stdout.write(str(check_migrations()))

        # if check_migrations():
        #     self.stdout.write("True")
        # else:
        #     self.stdout.write("False")
