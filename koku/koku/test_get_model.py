#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from . import database as kdb
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider


class TestGetModel(IamTestCase):
    def test_loader(self):
        """Test that the loader function populates the module-level dict"""
        kdb.DB_MODELS.clear()
        self.assertEqual(kdb.DB_MODELS, {})

        kdb._load_db_models()
        self.assertNotEqual(kdb.DB_MODELS, {})

    def test_getter_calls_loader(self):
        """Test that get_model() will load the DB_MODELS dict before checking it"""
        kdb.DB_MODELS.clear()
        self.assertEqual(kdb.DB_MODELS, {})

        p = kdb.get_model("provider")
        self.assertNotEqual(kdb.DB_MODELS, {})
        self.assertEqual(p, Provider)

    def test_getter(self):
        """Test that get_model() will return a model class"""
        self.assertEqual(kdb.get_model("Provider"), Provider)
        self.assertEqual(kdb.get_model("provider"), Provider)
        self.assertEqual(kdb.get_model("api_provider"), Provider)
        self.assertEqual(kdb.get_model("api.provider"), Provider)

    def test_getter_ambiguous(self):
        """Test that ambiguous model names must be app-qualified."""
        with self.assertRaises(KeyError):
            kdb.get_model("user")

        self.assertEqual(kdb.get_model("api.user"), User)
        self.assertNotEqual(kdb.get_model("auth.user"), User)

    def test_getter_notfound(self):
        """Test that a bad model key will raise KeyError"""
        with self.assertRaises(KeyError):
            kdb.get_model("___eek___")
