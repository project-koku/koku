#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
from datetime import date
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas

from . import type_json_transcode as xcode
from api.iam.test.iam_test_case import IamTestCase


class TestJSONTranscode(IamTestCase):
    def test_encode_norm(self):
        """Test that the encoder only works on speficied types"""
        dat = {"dat": 1}
        self.assertNotIn("_py_type", json.dumps(dat, cls=xcode.TypedJSONEncoder))

    def test_encode_decimal(self):
        """Test that the encoder enocdes Decimal"""
        dat = {"dat": Decimal("1")}
        self.assertIn("_py_type", json.dumps(dat, cls=xcode.TypedJSONEncoder))

    def test_encode_date(self):
        """Test that the encoder enocdes datetime.date"""
        dat = {"dat": date.today()}
        self.assertIn("_py_type", json.dumps(dat, cls=xcode.TypedJSONEncoder))

    def test_encode_datetime(self):
        """Test that the encoder enocdes datetime.datetime"""
        dat = {"dat": datetime.now().replace(tzinfo=ZoneInfo("UTC"))}
        self.assertIn("_py_type", json.dumps(dat, cls=xcode.TypedJSONEncoder))

    def test_encode_error(self):
        """Test that the encoder throws error on undefined, unhashable type"""
        with self.assertRaises(TypeError):
            dat = {"dat": pandas.DataFrame()}
            json.dumps(dat, cls=xcode.TypedJSONDecoder)

    def test_decode_norm(self):
        """Test that regular type is returned correctly"""
        dat = {"id": 1}
        jsn = json.dumps(dat, cls=xcode.TypedJSONEncoder)
        decoded_dat = json.loads(jsn, cls=xcode.TypedJSONDecoder)
        self.assertEqual(dat, decoded_dat)

    def test_decode_decimal(self):
        """Test that Decimal type is returned correctly"""
        dat = {"id": 1, "dat": Decimal("1")}
        jsn = json.dumps(dat, cls=xcode.TypedJSONEncoder)
        _decoded_dat = json.loads(jsn)
        self.assertEqual({"_py_type", "value"}, set(_decoded_dat["dat"]))
        self.assertEqual(_decoded_dat["dat"]["_py_type"], "Decimal")
        self.assertEqual(dat, json.loads(jsn, cls=xcode.TypedJSONDecoder))

    def test_decode_date(self):
        """Test that datetime.date type is returned correctly"""
        dat = {"id": 1, "dat": date.today()}
        jsn = json.dumps(dat, cls=xcode.TypedJSONEncoder)
        _decoded_dat = json.loads(jsn)
        self.assertEqual({"_py_type", "value"}, set(_decoded_dat["dat"]))
        self.assertEqual(_decoded_dat["dat"]["_py_type"], "date")
        self.assertEqual(dat, json.loads(jsn, cls=xcode.TypedJSONDecoder))

    def test_decode_datetime(self):
        """Test that datetime.datetime type is returned correctly"""
        dat = {"id": 1, "dat": datetime.now().replace(tzinfo=ZoneInfo("UTC"))}
        jsn = json.dumps(dat, cls=xcode.TypedJSONEncoder)
        _decoded_dat = json.loads(jsn)
        self.assertEqual({"_py_type", "value"}, set(_decoded_dat["dat"]))
        self.assertEqual(_decoded_dat["dat"]["_py_type"], "datetime")
        self.assertEqual(dat, json.loads(jsn, cls=xcode.TypedJSONDecoder))

    def test_decode_undefined(self):
        """Test that undefined type is returned correctly"""
        dat = {"id": 1, "dat": datetime.now().replace(tzinfo=ZoneInfo("UTC"))}
        jsn = json.dumps(dat, cls=xcode.TypedJSONEncoder).replace("datetime", "no_type_here")
        _decoded_dat = json.loads(jsn, cls=xcode.TypedJSONDecoder)
        self.assertEqual(_decoded_dat["dat"]["_py_type"], "no_type_here")
        self.assertEqual(_decoded_dat["dat"]["value"], str(dat["dat"]))
