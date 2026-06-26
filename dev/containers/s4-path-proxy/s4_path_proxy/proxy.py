"""HTTP proxy that rewrites S3 object keys between long logical and short storage paths."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import parse_qsl
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import urllib3
from aiohttp import web
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from s4_path_proxy.aws_chunked import prepare_outbound_body
from s4_path_proxy.mapper import decode_key
from s4_path_proxy.mapper import encode_key
from s4_path_proxy.mapper import load_path_maps
from s4_path_proxy.mapper import PathMaps

LOG = logging.getLogger(__name__)
HTTP = urllib3.PoolManager()

S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"
COPY_SOURCE_RE = re.compile(r"^/?([^/]+)/(.+)$")
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

RESPONSE_STRIP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _register_namespace() -> None:
    ET.register_namespace("", S3_NS)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _split_bucket_key(path: str) -> tuple[str | None, str]:
    """Path-style S3 URL path: /bucket or /bucket/key."""
    path = path.lstrip("/")
    if not path:
        return None, ""
    if "/" not in path:
        return path, ""
    bucket, key = path.split("/", 1)
    return bucket, unquote(key)


def _build_path(bucket: str | None, key: str) -> str:
    if bucket is None:
        return "/"
    if not key:
        return f"/{bucket}"
    # Hive partition keys use literal '=' in paths; do not percent-encode here or SigV4 breaks.
    return f"/{bucket}/{key}"


# Incoming SigV4 headers from the client are dropped; the proxy re-signs for the backend.
STRIP_INCOMING_X_AMZ = {
    "x-amz-date",
    "x-amz-content-sha256",
    "x-amz-security-token",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-algorithm",
    "x-amz-expires",
    "x-amz-signedheaders",
}


def _filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for name, value in headers:
        lower = name.lower()
        if lower in HOP_BY_HOP:
            continue
        if lower in STRIP_INCOMING_X_AMZ:
            continue
        if lower == "authorization":
            continue
        filtered[name] = value
    return filtered


def _encode_copy_source(value: str, maps: PathMaps) -> str:
    match = COPY_SOURCE_RE.match(value)
    if not match:
        return value
    bucket, key = match.group(1), unquote(match.group(2))
    return f"/{bucket}/{encode_key(key, maps)}"


def _decode_copy_source(value: str, maps: PathMaps) -> str:
    match = COPY_SOURCE_RE.match(value)
    if not match:
        return value
    bucket, key = match.group(1), unquote(match.group(2))
    return f"/{bucket}/{decode_key(key, maps)}"


def _rewrite_query(query: str, maps: PathMaps, *, encode: bool) -> str:
    if not query:
        return query
    transform = encode_key if encode else decode_key
    pairs: list[tuple[str, str]] = []
    for name, value in parse_qsl(query, keep_blank_values=True):
        if name in {"prefix", "marker", "start-after", "continuation-token", "key"}:
            pairs.append((name, transform(unquote(value), maps)))
        else:
            pairs.append((name, value))
    return urlencode(pairs, quote_via=quote)


def _rewrite_delete_body(body: bytes, maps: PathMaps, *, encode: bool) -> bytes:
    if not body:
        return body
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return body
    transform = encode_key if encode else decode_key
    for element in root.iter():
        if _local_name(element.tag) == "Key" and element.text:
            element.text = transform(element.text, maps)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rewrite_list_xml(body: bytes, maps: PathMaps) -> bytes:
    if not body:
        return body
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return body
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in {"Key", "Prefix"} and element.text:
            element.text = decode_key(element.text, maps)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


class S3PathProxy:
    def __init__(
        self,
        maps: PathMaps,
        backend_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self.maps = maps
        self.backend_url = backend_url.rstrip("/")
        self.credentials = Credentials(access_key, secret_key)
        self.region = region
        _register_namespace()

    def _backend_target_url(
        self,
        bucket: str | None,
        key: str,
        query: str,
        *,
        encode: bool,
    ) -> str:
        storage_key = encode_key(key, self.maps) if encode else decode_key(key, self.maps)
        path = _build_path(bucket, storage_key)
        storage_query = _rewrite_query(query, self.maps, encode=encode)
        backend_parts = urlsplit(self.backend_url)
        return urlunsplit((backend_parts.scheme, backend_parts.netloc, path, storage_query, ""))

    def _payload_hash(self, body: bytes) -> str:
        if not body:
            return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        return hashlib.sha256(body).hexdigest()

    def _sign_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, str]:
        headers = dict(headers)
        headers["x-amz-content-sha256"] = self._payload_hash(body)
        aws_request = AWSRequest(method=method, url=url, data=body, headers=headers)
        SigV4Auth(self.credentials, "s3", self.region).add_auth(aws_request)
        return dict(aws_request.headers.items())

    async def handle(self, request: web.Request) -> web.Response:
        body = await request.read()
        incoming_url = str(request.url)
        split = urlsplit(incoming_url)
        bucket, key = _split_bucket_key(split.path)
        query = split.query

        outbound_headers = _filter_headers(request.headers.items())
        backend_parts = urlsplit(self.backend_url)
        outbound_headers["Host"] = backend_parts.netloc
        outbound_body = prepare_outbound_body(request.method, outbound_headers, body)
        if outbound_body is not body:
            LOG.info(
                "decoded aws-chunked %s body: %s -> %s bytes",
                request.method,
                len(body),
                len(outbound_body),
            )

        if request.headers.get("x-amz-copy-source"):
            outbound_headers["x-amz-copy-source"] = _encode_copy_source(
                request.headers["x-amz-copy-source"], self.maps
            )

        if request.method == "POST" and "delete" in parse_qsl(query):
            outbound_body = _rewrite_delete_body(body, self.maps, encode=True)

        backend_url = self._backend_target_url(bucket, key, query, encode=True)
        signed_headers = self._sign_request(request.method, backend_url, outbound_headers, outbound_body)

        LOG.debug(
            "proxy %s %s -> %s",
            request.method,
            incoming_url,
            backend_url,
        )

        backend_response = HTTP.request(
            request.method,
            backend_url,
            body=outbound_body if outbound_body else None,
            headers=signed_headers,
            preload_content=False,
        )
        try:
            response_body = backend_response.read()
            response_headers = {k: v for k, v in backend_response.headers.items() if k.lower() not in RESPONSE_STRIP}

            if backend_response.status >= 400:
                LOG.warning(
                    "backend %s %s -> %s %s",
                    request.method,
                    incoming_url,
                    backend_response.status,
                    response_body[:500],
                )

            if request.method == "GET" and "list-type=2" in query and backend_response.status == 200:
                response_body = _rewrite_list_xml(response_body, self.maps)

            if backend_response.headers.get("x-amz-copy-source"):
                response_headers["x-amz-copy-source"] = _decode_copy_source(
                    backend_response.headers["x-amz-copy-source"], self.maps
                )

            return web.Response(
                body=response_body,
                status=backend_response.status,
                headers=response_headers,
            )
        finally:
            backend_response.release_conn()


def create_app(
    maps: PathMaps | None = None,
    backend_url: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    region: str | None = None,
) -> web.Application:
    config_path = os.environ.get("S4_PATH_MAPS") or None
    maps = maps or load_path_maps(config_path)
    backend_url = backend_url or os.environ.get("S4_BACKEND_URL", "http://koku-s4:7480")
    access_key = access_key or os.environ.get("S3_ACCESS_KEY", "s4admin")
    secret_key = secret_key or os.environ.get("S3_SECRET", "s4secret")
    region = region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    proxy = S3PathProxy(maps, backend_url, access_key, secret_key, region)
    app = web.Application(client_max_size=1024**3)

    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/healthz", health)
    app.router.add_route("*", "/{tail:.*}", proxy.handle)
    return app
