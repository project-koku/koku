#!/usr/bin/env python3
"""Tests for parse_kibana_ingress_payload_logs.py."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURE = SCRIPT_DIR / "fixtures" / "kibana_search_response.redacted.json"


def _load_parser_module():
    script_path = SCRIPT_DIR / "parse_kibana_ingress_payload_logs.py"
    spec = importlib.util.spec_from_file_location("parse_kibana_ingress_payload_logs", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestParseKibanaIngressPayloadLogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = _load_parser_module()

    def test_loads_dev_tools_json_export(self):
        hits = self.parser.load_hits_from_export(FIXTURE)
        self.assertEqual(len(hits), 1)
        self.assertIn("Downloading Payload", hits[0]["@message"])

    def test_parse_hit_redacted_fixture(self):
        hits = self.parser.load_hits_from_export(FIXTURE)
        row = self.parser.parse_hit(hits[0])
        self.assertEqual(row["request_id"], "abc123def4567890abcdef1234567890")
        self.assertEqual(row["org_id"], "1234567")
        self.assertEqual(row["account"], "10001")
        self.assertEqual(row["cluster_id"], "cluster-uuid-placeholder")
        self.assertTrue(row["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
