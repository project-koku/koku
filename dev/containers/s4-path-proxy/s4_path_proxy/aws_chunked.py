"""Decode AWS SigV4 aws-chunked request bodies (Java SDK / Trino PUT payloads)."""
from __future__ import annotations


class AwsChunkedDecodeError(ValueError):
    """Raised when an aws-chunked body cannot be parsed."""


def decode_aws_chunked(body: bytes) -> bytes:
    """Extract raw payload bytes from an aws-chunked encoded stream."""
    if not body:
        return body

    out = bytearray()
    pos = 0
    while pos < len(body):
        line_end = body.find(b"\r\n", pos)
        if line_end < 0:
            raise AwsChunkedDecodeError("incomplete aws-chunked header")
        line = body[pos:line_end]
        pos = line_end + 2

        chunk_size_hex = line.split(b";", 1)[0]
        if not chunk_size_hex:
            raise AwsChunkedDecodeError("empty aws-chunked size line")
        try:
            chunk_size = int(chunk_size_hex, 16)
        except ValueError as exc:
            raise AwsChunkedDecodeError(f"invalid aws-chunked size: {chunk_size_hex!r}") from exc

        if chunk_size == 0:
            break

        end = pos + chunk_size
        if end > len(body):
            raise AwsChunkedDecodeError("truncated aws-chunked payload")
        out.extend(body[pos:end])
        pos = end
        if body[pos : pos + 2] == b"\r\n":
            pos += 2

    return bytes(out)


def is_aws_chunked_request(headers: dict[str, str], body: bytes) -> bool:
    """Return True when the request body uses AWS chunked streaming encoding."""
    lowered = {name.lower(): value for name, value in headers.items()}
    content_sha = lowered.get("x-amz-content-sha256", "")
    if content_sha.upper().startswith("STREAMING-"):
        return True
    if lowered.get("content-encoding", "").lower() == "aws-chunked":
        return True
    if body and b";chunk-signature=" in body[:256]:
        return True
    return False


def strip_chunked_request_headers(headers: dict[str, str]) -> None:
    """Remove headers that only apply to aws-chunked client uploads."""
    for name in list(headers):
        lower = name.lower()
        if lower in {"content-encoding", "x-amz-decoded-content-length", "x-amz-trailer"}:
            del headers[name]
        elif lower.startswith("x-amz-checksum-"):
            del headers[name]


def prepare_outbound_body(method: str, headers: dict[str, str], body: bytes) -> bytes:
    """Decode aws-chunked PUT/POST bodies before re-signing for the backend."""
    if method not in {"PUT", "POST"} or not body:
        return body
    if not is_aws_chunked_request(headers, body):
        return body

    decoded = decode_aws_chunked(body)
    strip_chunked_request_headers(headers)
    headers["Content-Length"] = str(len(decoded))
    return decoded
