#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db.utils import IntegrityError

from . import database as kdb
from api.iam.test.iam_test_case import IamTestCase


class TestFKViolation(IamTestCase):
    INTEGRITYERRORSTR = """insert or update on table "reporting_awscostentrybill" violates foreign key constraint "reporting_awscostent_provider_id_a08725b3_fk_api_provi"
DETAIL:  Key (provider_id)=(fbe0593a-1b83-4182-b23e-08cd190ed939) is not present in table "api_provider".
"""  # noqa
    INTEGRITYERROR = IntegrityError(INTEGRITYERRORSTR)

    def test_init_from_exception(self):
        """Test that the FKViolation class can init from an exception"""
        fkv = kdb.FKViolation(self.INTEGRITYERROR)
        self.assertTrue(fkv)

        fkv = kdb.FKViolation(ValueError("eek"))
        self.assertFalse(fkv)

    def test_init_from_str(self):
        """Test that the FKViolation class can init from a string"""
        fkv = kdb.FKViolation(self.INTEGRITYERRORSTR)
        self.assertTrue(fkv)

        fkv = kdb.FKViolation("eek")
        self.assertFalse(fkv)

    def test_str_repr(self):
        """Test that the FKViolation str and repr return the same result"""
        fkv = kdb.FKViolation(self.INTEGRITYERRORSTR)
        self.assertEqual(str(fkv), repr(fkv))

    def test_status_protected(self):
        """Test that the FKViolation status is protected"""
        fkv = kdb.FKViolation(self.INTEGRITYERRORSTR)
        with self.assertRaises(AttributeError):
            fkv.is_fk_violation = False

    def test_violation_parser_output(self):
        """Test that the FKViolation message parse for an exception stores the parts in the correct attributes"""
        fkv = kdb.FKViolation(self.INTEGRITYERROR)
        self.assertEqual(fkv.is_fk_violation, True)
        self.assertEqual(fkv.action, "insert or update")
        self.assertEqual(fkv.target_table, "reporting_awscostentrybill")
        self.assertEqual(fkv.reference_table, "api_provider")
        self.assertEqual(fkv.detected_key_values, "Key (provider_id)=(fbe0593a-1b83-4182-b23e-08cd190ed939)")

    def test_not_violation_parser_output(self):
        """Test that the FKViolation message parse for non-exception does not set the parts attributes"""
        fkv = kdb.FKViolation("This is not an exception")
        self.assertEqual(fkv.is_fk_violation, False)
        self.assertIsNone(fkv.action)
        self.assertIsNone(fkv.target_table)
        self.assertIsNone(fkv.reference_table)
        self.assertIsNone(fkv.detected_key_values)
