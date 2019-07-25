from django.core.management.base import BaseCommand
from masu.external.kafka_msg_handler import initialize_kafka_handler

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        print('Starting Kafka handler')
        initialize_kafka_handler()
