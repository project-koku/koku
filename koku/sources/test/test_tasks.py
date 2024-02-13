#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Sources Kafka Listener handler."""
from unittest.mock import patch
from uuid import uuid4

from django.db.models.signals import post_save
from django.test import TestCase
from django.test.utils import override_settings

from api.provider.models import Sources
from koku.middleware import IdentityHeaderMiddleware
from sources.api.source_status import SourceStatus
from sources.config import Config
from sources.kafka_listener import storage_callback
from sources.tasks import delete_source
from sources.tasks import delete_source_beat
from sources.tasks import source_status_beat


class SourcesTasksTest(TestCase):
    """Test Cases for the Sources Tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)
        account = "12345"
        org_id = "3333333"
        IdentityHeaderMiddleware.create_customer(account, org_id)

    def setUp(self):
        """Setup the test method."""
        super().setUp()
        self.aws_source = {
            "source_id": 10,
            "source_uuid": uuid4(),
            "name": "ProviderAWS",
            "source_type": "AWS",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}},
            "billing_source": {"data_source": {"bucket": "fake-bucket"}},
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "account_id": "org1234567",
            "org_id": "org1234567",
            "offset": 10,
            "pending_delete": True,
        }
        self.aws_local_source = {
            "source_id": 11,
            "source_uuid": uuid4(),
            "koku_uuid": uuid4(),
            "name": "ProviderAWS Local",
            "source_type": "AWS-local",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}},
            "billing_source": {"data_source": {"bucket": "fake-local-bucket"}},
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "account_id": "org1234567",
            "org_id": "org1234567",
            "offset": 11,
        }

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_execute_source_destroy_beat(self):
        """Test to execute the beat source delete."""
        source_id_aws = self.aws_source.get("source_id")
        source_id_local = self.aws_local_source.get("source_id")
        for s in (self.aws_source, self.aws_local_source):
            provider = Sources(**s)
            provider.save()

        delete_source_beat()

        self.assertEqual(Sources.objects.filter(source_id=source_id_aws).exists(), False)
        self.assertEqual(Sources.objects.filter(source_id=source_id_local).exists(), True)

    def test_execute_source_destroy_double_delete(self):
        """Test to execute source delete of same source."""
        source_id_aws = self.aws_source.get("source_id")
        source_id_local = self.aws_local_source.get("source_id")
        for s in (self.aws_source, self.aws_local_source):
            provider = Sources(**s)
            provider.save()

        delete_source(
            source_id_aws,
            self.aws_source["auth_header"],
            self.aws_source["source_uuid"],
            self.aws_source["account_id"],
            self.aws_source["org_id"],
        )

        try:
            delete_source(
                source_id_aws,
                self.aws_source["auth_header"],
                self.aws_source["source_uuid"],
                self.aws_source["account_id"],
                self.aws_source["org_id"],
            )
        except Exception as error:
            self.fail(f"test_execute_koku_provider_op_destroy test failure: {error}")

        self.assertEqual(Sources.objects.filter(source_id=source_id_aws).exists(), False)
        self.assertEqual(Sources.objects.filter(source_id=source_id_local).exists(), True)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_execute_source_status_beat(self):
        """Test to execute the beat source status."""
        source_id_local = self.aws_local_source.get("source_id")

        provider = Sources(**self.aws_local_source)
        provider.save()

        self.assertEqual(Sources.objects.filter(source_id=source_id_local).exists(), True)

        with patch.object(SourceStatus, "push_status") as mock_push:
            source_status_beat()
            mock_push.assert_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_execute_source_status_beat_missing(self):
        """Test to execute the beat source status when a source is missing."""
        source_id_local = self.aws_local_source.get("source_id")

        provider = Sources(**self.aws_local_source)
        provider.save()
        provider.delete()

        self.assertEqual(Sources.objects.filter(source_id=source_id_local).exists(), False)

        with patch.object(SourceStatus, "push_status") as mock_push:
            source_status_beat()
            mock_push.assert_not_called()
