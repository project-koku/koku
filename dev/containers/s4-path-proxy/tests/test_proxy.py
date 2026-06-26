"""Tests for S3 path proxy HTTP helpers."""
from s4_path_proxy.proxy import _filter_headers


def test_filter_headers_preserves_user_metadata():
    headers = [
        ("Authorization", "AWS4-HMAC-SHA256 ..."),
        ("x-amz-date", "20260625T000000Z"),
        ("x-amz-content-sha256", "abc"),
        ("x-amz-meta-manifestid", "12345"),
        ("x-amz-meta-reportdatestart", "2026-01-01"),
        ("Content-Type", "binary/octet-stream"),
    ]
    filtered = _filter_headers(headers)
    assert "Authorization" not in filtered
    assert "x-amz-date" not in filtered
    assert filtered["x-amz-meta-manifestid"] == "12345"
    assert filtered["x-amz-meta-reportdatestart"] == "2026-01-01"
    assert filtered["Content-Type"] == "binary/octet-stream"
