#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid

from . import database as kdb
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider


class TestDeleteSQL(IamTestCase):
    def test_delete_query_sql(self):
        """Test that get_delete_sql returns expected SQL statement"""
        provider = Provider.objects.first()
        provider_query = Provider.objects.filter(uuid=provider.uuid)
        expected = """delete from "api_provider" where "api_provider"."uuid" = %s"""
        del_sql, params = kdb.get_delete_sql(provider_query)

        self.assertTrue(expected in del_sql.lower())
        self.assertTrue(provider.uuid in params)

    def test_execute_delete_sql(self):
        """Test that execute_delete_sql runs the delete SQL"""
        # Add a bogus provider
        p = Provider(
            uuid=uuid.uuid4(), name="eek_provider_1", type=Provider.PROVIDER_OCP, setup_complete=False, active=True
        )
        p.save()
        # Delete it with SQL
        del_count = kdb.execute_delete_sql(Provider.objects.filter(pk=p.pk))

        self.assertEqual(del_count, 1)
        self.assertIsNone(Provider.objects.filter(pk=p.pk).first())
