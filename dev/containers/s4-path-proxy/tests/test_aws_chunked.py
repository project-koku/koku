"""Tests for aws-chunked request decoding."""
import pytest
from s4_path_proxy.aws_chunked import AwsChunkedDecodeError
from s4_path_proxy.aws_chunked import decode_aws_chunked
from s4_path_proxy.aws_chunked import is_aws_chunked_request
from s4_path_proxy.aws_chunked import prepare_outbound_body


def _encode_chunks(*chunks: bytes) -> bytes:
    sig = "a" * 64
    out = bytearray()
    for chunk in chunks:
        out.extend(f"{len(chunk):x};chunk-signature={sig}\r\n".encode())
        out.extend(chunk)
        out.extend(b"\r\n")
    out.extend(f"0;chunk-signature={sig}\r\n\r\n".encode())
    return bytes(out)


def test_decode_aws_chunked_single_chunk():
    payload = b"PAR1" + b"x" * 100 + b"PAR1"
    assert decode_aws_chunked(_encode_chunks(payload)) == payload


def test_decode_aws_chunked_multiple_chunks():
    first, second = b"hello", b"world"
    assert decode_aws_chunked(_encode_chunks(first, second)) == first + second


def test_decode_aws_chunked_truncated_raises():
    body = b"a;chunk-signature=" + b"a" * 64 + b"\r\nhi"
    with pytest.raises(AwsChunkedDecodeError):
        decode_aws_chunked(body)


def test_is_aws_chunked_request_detects_streaming_sha_header():
    headers = {"x-amz-content-sha256": "STREAMING-AWS4-HMAC-SHA256-PAYLOAD"}
    assert is_aws_chunked_request(headers, b"raw") is True


def test_prepare_outbound_body_decodes_and_rewrites_length():
    payload = b"PAR1payloadPAR1"
    headers = {
        "x-amz-content-sha256": "STREAMING-AWS4-HMAC-SHA256-PAYLOAD",
        "content-encoding": "aws-chunked",
        "x-amz-decoded-content-length": str(len(payload)),
        "x-amz-checksum-crc32": "abc",
    }
    outbound = prepare_outbound_body("PUT", headers, _encode_chunks(payload))
    assert outbound == payload
    assert headers["Content-Length"] == str(len(payload))
    assert "content-encoding" not in {k.lower() for k in headers}
    assert "x-amz-checksum-crc32" not in {k.lower() for k in headers}
