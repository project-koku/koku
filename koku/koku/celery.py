"""Celery configuration for the Koku project."""
from __future__ import absolute_import, unicode_literals

import logging
import os

import django
from django.apps import apps
from django.conf import settings
from celery import Celery
from celery.signals import after_setup_logger


LOGGER = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'koku.settings')

LOGGER.info('Starting celery.')
# Django setup is required *before* Celery app can start correctly.
django.setup()
LOGGER.info('Django setup.')

APP = Celery('koku', broker=django.conf.settings.CELERY_BROKER_URL)
APP.config_from_object('django.conf:settings', namespace='CELERY')
LOGGER.info('Celery autodiscover tasks.')
# APP.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
APP.autodiscover_tasks()

# The signal decorator is associated with the
# following method signature, but args and kwargs are not currently utilized.
# Learn more about celery signals here:
# http://docs.celeryproject.org/en/v4.2.0/userguide/signals.html#logging-signals
@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):  # pylint: disable=unused-argument
    """Add logging for celery with optional cloud watch."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
