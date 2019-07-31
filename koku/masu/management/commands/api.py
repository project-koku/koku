from django.core.management.base import BaseCommand
from masu.celery.tasks import check_report_updates

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        print('Starting Internal Masu API Server')
        async_download_result = check_report_updates.delay()
        print(str(async_download_result))
