''' django database settings '''
import os

from django.conf import settings

from .settings import env

# pylint: disable=invalid-name
engines = {
    'sqlite': 'django.db.backends.sqlite3',
    'postgresql': 'django.db.backends.postgresql_psycopg2',
    'mysql': 'django.db.backends.mysql',
}


def config():
    ''' database config '''
    service_name = env.get_value('DATABASE_SERVICE_NAME', default='').upper().replace('-', '_')
    if service_name:
        engine = engines.get(env.get_value('DATABASE_ENGINE'), engines['sqlite'])
    else:
        engine = engines['sqlite']
    name = env.get_value('DATABASE_NAME')
    if not name and engine == engines['sqlite']:
        name = os.path.join(settings.BASE_DIR, 'db.sqlite3')
    return {
        'ENGINE': engine,
        'NAME': name,
        'USER': env.get_value('DATABASE_USER'),
        'PASSWORD': env.get_value('DATABASE_PASSWORD'),
        'HOST': env.get_value('{}_SERVICE_HOST'.format(service_name)),
        'PORT': env.get_value('{}_SERVICE_PORT'.format(service_name)),
    }
