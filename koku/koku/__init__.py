"""Configurations for the Koku Project."""

from .celery import APP as celery_app

__all__ = ('celery_app',)
