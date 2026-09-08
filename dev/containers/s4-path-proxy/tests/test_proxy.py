"""Tests for S3 path proxy HTTP helpers."""
from s4_path_proxy.proxy import _filter_headers
from s4_path_proxy.proxy import _is_bulk_delete_request
from s4_path_proxy.proxy import _is_list_objects_request
from s4_path_proxy.proxy import _set_header


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


def test_is_bulk_delete_request_detects_delete_query_param():
    assert _is_bulk_delete_request("POST", "delete")
    assert _is_bulk_delete_request("POST", "delete=&foo=bar")
    assert not _is_bulk_delete_request("POST", "uploads")
    assert not _is_bulk_delete_request("GET", "delete")


def test_is_list_objects_request_for_bucket_root_get():
    assert _is_list_objects_request("GET", "koku-bucket", "")
    assert not _is_list_objects_request("GET", "koku-bucket", "some/key")
    assert not _is_list_objects_request("POST", "koku-bucket", "")


def test_set_header_replaces_case_insensitive_duplicate():
    headers = {"X-Amz-Copy-Source": "/bucket/old", "content-type": "text/plain"}
    _set_header(headers, "x-amz-copy-source", "/bucket/new")
    assert headers == {"x-amz-copy-source": "/bucket/new", "content-type": "text/plain"}
