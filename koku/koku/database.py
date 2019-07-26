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

from .env import ENVIRONMENT

# pylint: disable=invalid-name
engines = {
    'sqlite': 'django.db.backends.sqlite3',
    'postgresql': 'tenant_schemas.postgresql_backend',
    'mysql': 'django.db.backends.mysql',
}


def _cert_config(db_config, database_cert):
    """Add certificate configuration as needed."""
    if database_cert:
        cert_file = '/etc/ssl/certs/server.pem'
        db_options = {
            'OPTIONS': {
                'sslmode': 'verify-full',
                'sslrootcert': cert_file
            }
        }
        db_config.update(db_options)
    return db_config


def config():
    """Database config."""
    service_name = ENVIRONMENT.get_value('DATABASE_SERVICE_NAME',
                                         default='').upper().replace('-', '_')
    if service_name:
        engine = engines.get(ENVIRONMENT.get_value('DATABASE_ENGINE'),
                             engines['postgresql'])
    else:
        engine = engines['postgresql']

    name = ENVIRONMENT.get_value('DATABASE_NAME', default='postgres')

    if not name and engine == engines['sqlite']:
        name = os.path.join(settings.BASE_DIR, 'db.sqlite3')

    db_config = {
        'ENGINE': engine,
        'NAME': name,
        'USER': ENVIRONMENT.get_value('DATABASE_USER', default='postgres'),
        'PASSWORD': ENVIRONMENT.get_value('DATABASE_PASSWORD', default='postgres'),
        'HOST': ENVIRONMENT.get_value('{}_SERVICE_HOST'.format(service_name),
                                      default='localhost'),
        'PORT': ENVIRONMENT.get_value('{}_SERVICE_PORT'.format(service_name),
                                      default=15432),
    }

    database_cert = ENVIRONMENT.get_value('DATABASE_SERVICE_CERT', default=None)
    return _cert_config(db_config, database_cert)
