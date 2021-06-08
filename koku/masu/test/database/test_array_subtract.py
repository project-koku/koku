#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ProviderDBAccessor utility object."""
import json

from django.db import connection

from masu.test import MasuTestCase


class ArraySubtractTest(MasuTestCase):
    """Test Cases for array_subtract db function."""

    def test_array_subtract(self):
        """Test basic array_subtract invocation."""
        arr1 = [1, 2, 3, 4, 5]
        arr2 = [0, 2, 4, 6, 8]
        diff = set(arr1) - set(arr2)
        cur = connection.cursor()
        cur.execute("select public.array_subtract(%s::int[], %s::int[]);", (arr1, arr2))
        res = cur.fetchone()
        self.assertTrue(res is not None)
        res = res[0]
        self.assertIsInstance(res, list)
        self.assertEqual(diff, set(res))

    def test_array_subtract_null_input(self):
        """Test basic array_subtract invocation with null input."""
        arr1 = [1, 2, 3, 4, 5]
        arr2 = None
        cur = connection.cursor()
        cur.execute("select public.array_subtract(%s::int[], %s::int[]);", (arr1, arr2))
        res = cur.fetchone()
        self.assertTrue(res is not None)
        res = res[0]
        self.assertIsNone(res)

    def test_sql_enabled_keys_tag_filter(self):
        """Test enable keys tag update via SQL."""
        data_tags = {"app": "eek", "mode": "test", "version": "1.0.0", "author": "dude"}
        enabled_keys = ["app", "version"]
        enabled_data_tags = {k: v for k, v in data_tags.items() if k in enabled_keys}
        data_tags_str = json.dumps(data_tags)
        cur = connection.cursor()
        cur.execute(
            """
select case %s::text[]
           when '{}'::text[] then %s::jsonb
           else (%s::jsonb - array_subtract(array(select jsonb_object_keys(%s::jsonb))::text[], %s::text[]))::jsonb
       end::jsonb;
""",
            (enabled_keys, data_tags_str, data_tags_str, data_tags_str, enabled_keys),
        )
        res = cur.fetchone()
        self.assertTrue(res is not None)
        res = res[0]
        if isinstance(res, str):
            res = json.loads(res)
        self.assertEqual(res, enabled_data_tags)

    def test_sql_all_enabled_keys_tag_filter(self):
        """Test enable keys tag update via SQL when all tags are enabled."""
        data_tags = {"app": "eek", "mode": "test", "version": "1.0.0", "author": "dude"}
        data_tags_str = json.dumps(data_tags)
        cur = connection.cursor()
        enabled_keys = list(data_tags)
        cur.execute(
            """
select case %s::text[]
           when '{}'::text[] then %s::jsonb
           else (%s::jsonb - array_subtract(array(select jsonb_object_keys(%s::jsonb))::text[], %s::text[]))::jsonb
       end::jsonb;
""",
            (enabled_keys, data_tags_str, data_tags_str, data_tags_str, enabled_keys),
        )
        res = cur.fetchone()
        self.assertTrue(res is not None)
        res = res[0]
        if isinstance(res, str):
            res = json.loads(res)
        self.assertEqual(res, data_tags)

    def test_sql_undefined_enabled_keys_tag_filter(self):
        """Test enable keys tag update via SQL no enabled tags defined."""
        data_tags = {"app": "eek", "mode": "test", "version": "1.0.0", "author": "dude"}
        data_tags_str = json.dumps(data_tags)
        cur = connection.cursor()
        enabled_keys = []
        cur.execute(
            """
select case %s::text[]
           when '{}'::text[] then %s::jsonb
           else (%s::jsonb - array_subtract(array(select jsonb_object_keys(%s::jsonb))::text[], %s::text[]))::jsonb
       end::jsonb;
""",
            (enabled_keys, data_tags_str, data_tags_str, data_tags_str, enabled_keys),
        )
        res = cur.fetchone()
        self.assertTrue(res is not None)
        res = res[0]
        if isinstance(res, str):
            res = json.loads(res)
        self.assertEqual(res, data_tags)
