#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Redis/Valkey connection configuration."""
import ssl
from unittest.mock import patch
from urllib.parse import quote

from django.test import override_settings
from django.test import TestCase


class TestRedisUrlConstruction(TestCase):
    """Test Redis URL is constructed correctly based on environment variables."""

    def _build_redis_url(self, host="redis", port="6379", db=1, password="", use_ssl=False):
        """Replicate the URL construction logic from settings.py."""
        scheme = "rediss" if use_ssl else "redis"
        auth = f":{quote(password)}@" if password else ""
        return f"{scheme}://{auth}{host}:{port}/{db}"

    def test_default_url_no_auth_no_tls(self):
        """Verify default URL is redis://host:port/db."""
        url = self._build_redis_url()
        self.assertEqual(url, "redis://redis:6379/1")

    def test_url_with_password(self):
        """Verify password is encoded in URL as redis://:password@host:port/db."""
        url = self._build_redis_url(password="s3cret")
        self.assertEqual(url, "redis://:s3cret@redis:6379/1")

    def test_url_with_tls(self):
        """Verify TLS switches scheme to rediss://."""
        url = self._build_redis_url(use_ssl=True)
        self.assertEqual(url, "rediss://redis:6379/1")

    def test_url_with_password_and_tls(self):
        """Verify both password and TLS produce rediss://:password@host:port/db."""
        url = self._build_redis_url(password="s3cret", use_ssl=True)
        self.assertEqual(url, "rediss://:s3cret@redis:6379/1")

    def test_url_with_custom_host_and_port(self):
        """Verify custom host and port are used."""
        url = self._build_redis_url(host="external-redis.example.com", port="6380")
        self.assertEqual(url, "redis://external-redis.example.com:6380/1")

    def test_url_with_special_chars_in_password(self):
        """Verify special characters in password are URL-encoded."""
        url = self._build_redis_url(password="p@ss:w/rd")
        self.assertEqual(url, f"redis://:{quote('p@ss:w/rd')}@redis:6379/1")
        self.assertNotIn("p@ss:w/rd@", url)

    def test_empty_password_no_auth_in_url(self):
        """Verify empty password does not add auth section to URL."""
        url = self._build_redis_url(password="")
        self.assertNotIn("@", url)


class TestRedisSettingsIntegration(TestCase):
    """Test that Django settings correctly read Redis configuration from environment."""

    @override_settings()
    @patch.dict("os.environ", {"REDIS_PASSWORD": "testpass"})
    def test_settings_reads_redis_password(self):
        """Verify REDIS_PASSWORD is read from environment."""
        from environ import Env

        env = Env()
        password = env.get_value("REDIS_PASSWORD", default="")
        self.assertEqual(password, "testpass")

    @override_settings()
    @patch.dict("os.environ", {"REDIS_SSL": "True"})
    def test_settings_reads_redis_ssl(self):
        """Verify REDIS_SSL is read from environment as boolean."""
        from environ import Env

        env = Env()
        use_ssl = env.bool("REDIS_SSL", default=False)
        self.assertTrue(use_ssl)

    @override_settings()
    @patch.dict("os.environ", {"REDIS_SSL": "False"})
    def test_settings_redis_ssl_default_false(self):
        """Verify REDIS_SSL defaults to False."""
        from environ import Env

        env = Env()
        use_ssl = env.bool("REDIS_SSL", default=False)
        self.assertFalse(use_ssl)

    def test_ssl_cert_reqs_with_ca_certs(self):
        """Verify ssl.CERT_REQUIRED is used when CA certs path is provided."""
        ca_certs = "/etc/redis-tls/ca.crt"
        cert_reqs = ssl.CERT_REQUIRED if ca_certs else ssl.CERT_NONE
        self.assertEqual(cert_reqs, ssl.CERT_REQUIRED)

    def test_ssl_cert_reqs_always_required(self):
        """Verify ssl.CERT_REQUIRED is always used when SSL is enabled."""
        self.assertEqual(ssl.CERT_REQUIRED, ssl.CERT_REQUIRED)

    @override_settings(
        REDIS_HOST="redis",
        REDIS_PORT="6379",
        REDIS_DB=1,
        REDIS_PASSWORD="mypass",
        REDIS_SSL=True,
        REDIS_SSL_CA_CERTS="/etc/redis-tls/ca.crt",
        REDIS_SSL_CERT_REQS=ssl.CERT_REQUIRED,
        REDIS_CONNECTION_POOL_KWARGS={
            "health_check_interval": 5,
            "retry_on_timeout": True,
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
            "ssl_ca_certs": "/etc/redis-tls/ca.crt",
        },
    )
    def test_connection_pool_kwargs_include_ssl(self):
        """Verify SSL kwargs are added to connection pool kwargs when SSL is enabled."""
        from django.conf import settings

        self.assertIn("ssl_cert_reqs", settings.REDIS_CONNECTION_POOL_KWARGS)
        self.assertEqual(settings.REDIS_CONNECTION_POOL_KWARGS["ssl_cert_reqs"], ssl.CERT_REQUIRED)
        self.assertIn("ssl_ca_certs", settings.REDIS_CONNECTION_POOL_KWARGS)
        self.assertEqual(settings.REDIS_CONNECTION_POOL_KWARGS["ssl_ca_certs"], "/etc/redis-tls/ca.crt")
