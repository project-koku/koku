"""Django database settings."""
import os

from django.conf import settings

from .env import ENVIRONMENT

# pylint: disable=invalid-name
engines = {
    'sqlite': 'django.db.backends.sqlite3',
    'postgresql': 'django.db.backends.postgresql_psycopg2',
    'mysql': 'django.db.backends.mysql',
}


def config():
    """Database config."""
    service_name = ENVIRONMENT.get_value('DATABASE_SERVICE_NAME',
                                         default='').upper().replace('-', '_')
    if service_name:
        engine = engines.get(ENVIRONMENT.get_value('DATABASE_ENGINE'),
                             engines['postgresql'])
    else:
        engine = engines['postgresql']

    name = ENVIRONMENT.get_value('DATABASE_NAME', default=None)

    if not name and engine == engines['sqlite']:
        name = os.path.join(settings.BASE_DIR, 'db.sqlite3')

    return {
        'ENGINE': engine,
        'NAME': name,
        'USER': ENVIRONMENT.get_value('DATABASE_USER', default=None),
        'PASSWORD': ENVIRONMENT.get_value('DATABASE_PASSWORD', default=None),
        'HOST': ENVIRONMENT.get_value('{}_SERVICE_HOST'.format(service_name),
                                      default=None),
        'PORT': ENVIRONMENT.get_value('{}_SERVICE_PORT'.format(service_name),
                                      default=None),
    }
