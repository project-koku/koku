"""Tests for S4 path key translation."""
from pathlib import Path

import pytest
from s4_path_proxy.mapper import decode_key
from s4_path_proxy.mapper import encode_key
from s4_path_proxy.mapper import is_warehouse_key
from s4_path_proxy.mapper import load_path_maps

MAPS = load_path_maps(Path(__file__).resolve().parent.parent / "path_maps.yaml")

LONGEST_OCP_CLOUD_KEY = (
    "data/org1234567.db/managed_reporting_ocpazurecostlineitem_project_daily_summary_temp/"
    "source=550e8400-e29b-41d4-a716-446655440000/"
    "ocp_source=660e8400-e29b-41d4-a716-446655440001/"
    "year=2026/month=06/day=24/"
    "20260624_103045_1_2_3_abcdef01-2345-6789-abcd-ef0123456789.parquet"
)

PARQUET_EXTERNAL_KEY = (
    "data/parquet/org1234567/AWS/source=550e8400-e29b-41d4-a716-446655440000/year=2026/month=06/file.parquet"
)


class TestWarehouseDetection:
    def test_hive_warehouse_key(self):
        assert is_warehouse_key("data/org1234567.db/managed_aws_openshift_daily_temp/x")

    def test_parquet_external_not_warehouse(self):
        assert not is_warehouse_key(PARQUET_EXTERNAL_KEY)


class TestEncodeDecode:
    @pytest.mark.parametrize(
        "long_key",
        [
            "data/org1234567.db/managed_aws_openshift_daily_temp/source=abc/file.parquet",
            "data/org1234567.db/managed_reporting_ocpgcpcostlineitem_project_daily_summary/"
            "source=a/ocp_source=b/year=2026/month=01/day=01/f.parquet",
            "data/org1234567.db/reporting_ocpusagelineitem_daily_summary/source=a/year=2026/month=01/day=01/f",
            LONGEST_OCP_CLOUD_KEY,
        ],
    )
    def test_round_trip(self, long_key: str):
        short_key = encode_key(long_key, MAPS)
        assert short_key != long_key
        assert decode_key(short_key, MAPS) == long_key

    def test_schema_pattern_for_other_org(self):
        long_key = "data/org9999999.db/managed_gcp_openshift_daily_temp/part/file"
        short_key = encode_key(long_key, MAPS)
        assert short_key.startswith("o9999999/")
        assert decode_key(short_key, MAPS) == long_key

    def test_explicit_dev_schema_uses_single_digit(self):
        long_key = "data/org1234567.db/managed_aws_openshift_daily_temp/x"
        assert encode_key(long_key, MAPS).startswith("1/")

    def test_non_warehouse_passthrough(self):
        assert encode_key(PARQUET_EXTERNAL_KEY, MAPS) == PARQUET_EXTERNAL_KEY
        assert decode_key(PARQUET_EXTERNAL_KEY, MAPS) == PARQUET_EXTERNAL_KEY

    def test_unknown_table_only_schema_shortened(self):
        long_key = "data/org1234567.db/some_future_table/part/file"
        short_key = encode_key(long_key, MAPS)
        assert short_key == "1/some_future_table/part/file"
        assert decode_key(short_key, MAPS) == long_key


class TestFilenameLength:
    def test_longest_ocp_cloud_key_under_linux_limit(self):
        short_key = encode_key(LONGEST_OCP_CLOUD_KEY, MAPS)
        assert len(short_key) <= 255, f"encoded key length {len(short_key)} > 255: {short_key!r}"

    def test_savings_on_longest_key(self):
        short_key = encode_key(LONGEST_OCP_CLOUD_KEY, MAPS)
        saved = len(LONGEST_OCP_CLOUD_KEY) - len(short_key)
        assert saved >= 50
