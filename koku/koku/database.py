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
"""Django database settings."""
import os

from django.conf import settings
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.contrib.postgres.fields.jsonb import KeyTransform
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db import OperationalError
from django.db.migrations.executor import MigrationExecutor
from django.db.models import DecimalField
from django.db.models.aggregates import Func

from .env import ENVIRONMENT

engines = {
    "sqlite": "django.db.backends.sqlite3",
    "postgresql": "tenant_schemas.postgresql_backend",
    "mysql": "django.db.backends.mysql",
}


def _cert_config(db_config, database_cert):
    """Add certificate configuration as needed."""
    if database_cert:
        cert_file = "/etc/ssl/certs/server.pem"
        db_options = {"OPTIONS": {"sslmode": "verify-full", "sslrootcert": cert_file}}
        db_config.update(db_options)
    return db_config


def config():
    """Database config."""
    service_name = ENVIRONMENT.get_value("DATABASE_SERVICE_NAME", default="").upper().replace("-", "_")
    if service_name:
        engine = engines.get(ENVIRONMENT.get_value("DATABASE_ENGINE"), engines["postgresql"])
    else:
        engine = engines["postgresql"]

    name = ENVIRONMENT.get_value("DATABASE_NAME", default="postgres")

    if not name and engine == engines["sqlite"]:
        name = os.path.join(settings.BASE_DIR, "db.sqlite3")

    db_config = {
        "ENGINE": engine,
        "NAME": name,
        "USER": ENVIRONMENT.get_value("DATABASE_USER", default="postgres"),
        "PASSWORD": ENVIRONMENT.get_value("DATABASE_PASSWORD", default="postgres"),
        "HOST": ENVIRONMENT.get_value(f"{service_name}_SERVICE_HOST", default="localhost"),
        "PORT": ENVIRONMENT.get_value(f"{service_name}_SERVICE_PORT", default=15432),
    }

    database_cert = ENVIRONMENT.get_value("DATABASE_SERVICE_CERT", default=None)
    return _cert_config(db_config, database_cert)


def check_migrations():
    """
    Check the status of database migrations.
    The koku API server is responsible for running all database migrations.  This method
    will return the state of the database and whether or not all migrations have been completed.
    Hat tip to the Stack Overflow contributor: https://stackoverflow.com/a/31847406
    Returns:
        Boolean - True if database is available and migrations have completed.  False otherwise.
    """
    try:
        connection = connections[DEFAULT_DB_ALIAS]
        connection.prepare_database()
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        return not executor.migration_plan(targets)
    except OperationalError:
        return False


class JSONBBuildObject(Func):
    """Expose the Postgres jsonb_build_object function for use by ORM."""

    function = "jsonb_build_object"


class KeyDecimalTransform(KeyTextTransform):
    """Return a decimal for our numeric JSON."""

    output_field = DecimalField()

    def as_sql(self, compiler, connection):
        key_transforms = [self.key_name]
        previous = self.lhs
        while isinstance(previous, KeyTransform):
            key_transforms.insert(0, previous.key_name)
            previous = previous.lhs
        lhs, params = compiler.compile(previous)
        if len(key_transforms) > 1:
            return f"({lhs} {self.nested_operator} %s)", [key_transforms] + params
        try:
            lookup = int(self.key_name)
        except ValueError:
            lookup = self.key_name
        return f"({lhs} {self.operator} %s)::numeric", tuple(params) + (lookup,)
