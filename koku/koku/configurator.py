#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""
Handler module for gathering configuration data.
"""
from .env import ENVIRONMENT


CLOWDER_ENABLED = ENVIRONMENT.bool("CLOWDER_ENABLED", default=False)
if CLOWDER_ENABLED:
    from app_common_python import ObjectBuckets, LoadedConfig, KafkaTopics, DependencyEndpoints


class Configurator:
    """Obtain configuration based on mode."""

    @staticmethod
    def is_clowder_enabled():
        """Check if clowder is enabled."""
        return CLOWDER_ENABLED

    @staticmethod
    def get_feature_flag_host():
        """Obtain feature flag (Unleash) host."""
        pass

    @staticmethod
    def get_feature_flag_port():
        """Obtain feature flag (Unleash) port."""
        pass

    @staticmethod
    def get_feature_flag_token():
        """Obtain feature flag (Unleash) api token."""
        pass

    @staticmethod
    def get_in_memory_db_host():
        """Obtain in memory (redis) db host."""
        pass

    @staticmethod
    def get_in_memory_db_port():
        """Obtain in memory (redis) db port."""
        pass

    @staticmethod
    def get_kafka_broker_host():
        """Obtain kafka broker host address."""
        pass

    @staticmethod
    def get_kafka_broker_port():
        """Obtain kafka broker port."""
        pass

    @staticmethod
    def get_kafka_topic(requestedName: str):
        """Obtain kafka topic."""
        pass

    @staticmethod
    def get_cloudwatch_access_id():
        """Obtain cloudwatch access id."""
        pass

    @staticmethod
    def get_cloudwatch_access_key():
        """Obtain cloudwatch access key."""
        pass

    @staticmethod
    def get_cloudwatch_region():
        """Obtain cloudwatch region."""
        pass

    @staticmethod
    def get_cloudwatch_log_group():
        """Obtain cloudwatch log group."""
        pass

    @staticmethod
    def get_object_store_endpoint():
        """Obtain object store endpoint."""
        pass

    @staticmethod
    def get_object_store_host():
        """Obtain object store host."""
        pass

    @staticmethod
    def get_object_store_port():
        """Obtain object store port."""
        pass

    @staticmethod
    def get_object_store_tls():
        """Obtain object store secret key."""
        pass

    @staticmethod
    def get_object_store_access_key(requestedName: str = ""):
        """Obtain object store access key."""
        pass

    @staticmethod
    def get_object_store_secret_key(requestedName: str = ""):
        """Obtain object store secret key."""
        pass

    @staticmethod
    def get_object_store_bucket(requestedName: str = ""):
        """Obtain object store bucket."""
        pass

    @staticmethod
    def get_object_store_region(requestedName: str = ""):
        """Obtain object store bucket."""
        pass

    @staticmethod
    def get_database_name():
        """Obtain database name."""
        pass

    @staticmethod
    def get_database_user():
        """Obtain database user."""
        pass

    @staticmethod
    def get_database_password():
        """Obtain database password."""
        pass

    @staticmethod
    def get_database_host():
        """Obtain database host."""
        pass

    @staticmethod
    def get_database_port():
        """Obtain database port."""
        pass

    @staticmethod
    def get_database_ca():
        """Obtain database ca."""
        pass

    @staticmethod
    def get_database_ca_file():
        """Obtain database ca file."""
        pass

    @staticmethod
    def get_metrics_port():
        """Obtain metrics port."""
        pass

    @staticmethod
    def get_metrics_path():
        """Obtain metrics path."""
        pass

    @staticmethod
    def get_endpoint_host(app, name, default):
        """Obtain endpoint hostname."""
        pass

    @staticmethod
    def get_endpoint_port(app, name, default):
        """Obtain endpoint port."""
        pass


class EnvConfigurator(Configurator):
    """Returns information based on the environment data"""

    @staticmethod
    def get_feature_flag_host():
        """Obtain feature flag (Unleash) host."""
        return ENVIRONMENT.get_value("UNLEASH_HOST", default="unleash")

    @staticmethod
    def get_feature_flag_port():
        """Obtain feature flag (Unleash) port."""
        return ENVIRONMENT.get_value("UNLEASH_PORT", default="4242")

    @staticmethod
    def get_feature_flag_token():
        """Obtain feature flag (Unleash) port."""
        return ENVIRONMENT.get_value("UNLEASH_TOKEN", default="")

    @staticmethod
    def get_in_memory_db_host():
        """Obtain in memory (redis) db host."""
        return ENVIRONMENT.get_value("REDIS_HOST", default="redis")

    @staticmethod
    def get_in_memory_db_port():
        """Obtain in memory (redis) db port."""
        return ENVIRONMENT.get_value("REDIS_PORT", default="6379")

    @staticmethod
    def get_kafka_broker_host():
        """Obtain kafka broker host address."""
        return ENVIRONMENT.get_value("INSIGHTS_KAFKA_HOST", default="localhost")

    @staticmethod
    def get_kafka_broker_port():
        """Obtain kafka broker port."""
        return ENVIRONMENT.get_value("INSIGHTS_KAFKA_PORT", default="29092")

    @staticmethod
    def get_kafka_topic(requestedName: str):
        """Obtain kafka topic."""
        return requestedName

    @staticmethod
    def get_kafka_sasl():
        """Obtain kafka sasl"""
        return {}

    @staticmethod
    def get_kafka_cacert():
        """Obtain kafka CA Certificate"""
        return None

    @staticmethod
    def get_kafka_authtype():
        """Obtain kafka Authentication Type"""
        return None

    @staticmethod
    def get_cloudwatch_access_id():
        """Obtain cloudwatch access id."""
        return ENVIRONMENT.get_value("CW_AWS_ACCESS_KEY_ID", default=None)

    @staticmethod
    def get_cloudwatch_access_key():
        """Obtain cloudwatch access key."""
        return ENVIRONMENT.get_value("CW_AWS_SECRET_ACCESS_KEY", default=None)

    @staticmethod
    def get_cloudwatch_region():
        """Obtain cloudwatch region."""
        return ENVIRONMENT.get_value("CW_AWS_REGION", default="us-east-1")

    @staticmethod
    def get_cloudwatch_log_group():
        """Obtain cloudwatch log group."""
        return ENVIRONMENT.get_value("CW_LOG_GROUP", default="platform-dev")

    @staticmethod
    def get_object_store_endpoint():
        """Obtain object store endpoint."""
        S3_ENDPOINT = ENVIRONMENT.get_value("S3_ENDPOINT", default="s3.us-east-1.amazonaws.com")
        if not (S3_ENDPOINT.startswith("https://") or S3_ENDPOINT.startswith("http://")):
            S3_ENDPOINT = "https://" + S3_ENDPOINT
        return S3_ENDPOINT

    @staticmethod
    def get_object_store_host():
        """Obtain object store host."""
        # return ENVIRONMENT.get_value("S3_HOST", default=None)
        pass

    @staticmethod
    def get_object_store_port():
        """Obtain object store port."""
        # return ENVIRONMENT.get_value("S3_PORT", default=443)
        pass

    @staticmethod
    def get_object_store_tls():
        """Obtain object store secret key."""
        # return ENVIRONMENT.bool("S3_SECURE", default=False)
        pass

    @staticmethod
    def get_object_store_access_key(requestedName: str = ""):
        """Obtain object store access key."""
        return ENVIRONMENT.get_value("S3_ACCESS_KEY", default=None)

    @staticmethod
    def get_object_store_secret_key(requestedName: str = ""):
        """Obtain object store secret key."""
        return ENVIRONMENT.get_value("S3_SECRET", default=None)

    @staticmethod
    def get_object_store_bucket(requestedName: str = ""):
        """Obtain object store bucket."""
        return ENVIRONMENT.get_value("S3_BUCKET_NAME", default=requestedName)

    @staticmethod
    def get_object_store_region(requestedName: str = ""):
        """Obtain object store bucket."""
        return ENVIRONMENT.get_value("S3_REGION", default=requestedName)

    @staticmethod
    def get_database_name():
        """Obtain database name."""
        return ENVIRONMENT.get_value("DATABASE_NAME", default="postgres")

    @staticmethod
    def get_database_user():
        """Obtain database user."""
        return ENVIRONMENT.get_value("DATABASE_USER", default="postgres")

    @staticmethod
    def get_database_password():
        """Obtain database password."""
        return ENVIRONMENT.get_value("DATABASE_PASSWORD", default="postgres")

    @staticmethod
    def get_database_host():
        """Obtain database host."""
        SERVICE_NAME = ENVIRONMENT.get_value("DATABASE_SERVICE_NAME", default="").upper().replace("-", "_")
        return ENVIRONMENT.get_value(f"{SERVICE_NAME}_SERVICE_HOST", default="localhost")

    @staticmethod
    def get_database_port():
        """Obtain database port."""
        SERVICE_NAME = ENVIRONMENT.get_value("DATABASE_SERVICE_NAME", default="").upper().replace("-", "_")
        return ENVIRONMENT.get_value(f"{SERVICE_NAME}_SERVICE_PORT", default="15432")

    @staticmethod
    def get_database_ca():
        """Obtain database ca."""
        return ENVIRONMENT.get_value("DATABASE_SERVICE_CERT", default=None)

    @staticmethod
    def get_database_ca_file():
        """Obtain database ca file."""
        return ENVIRONMENT.get_value("DATABASE_SERVICE_CERTFILE", default="/etc/ssl/certs/server.pem")

    @staticmethod
    def get_metrics_port():
        """Obtain metrics port."""
        return 8080

    @staticmethod
    def get_metrics_path():
        """Obtain metrics path."""
        return "/metrics"

    @staticmethod
    def get_endpoint_host(app, name, default):
        """Obtain endpoint hostname."""
        svc = "_".join((app, name, "HOST")).replace("-", "_").upper()
        return ENVIRONMENT.get_value(svc, default=default)

    @staticmethod
    def get_endpoint_port(app, name, default):
        """Obtain endpoint port."""
        svc = "_".join((app, name, "PORT")).replace("-", "_").upper()
        return ENVIRONMENT.get_value(svc, default=default)


class ClowderConfigurator(Configurator):
    """Obtain configuration based on using Clowder and app-common."""

    @staticmethod
    def get_feature_flag_host():
        """Obtain feature flag (Unleash) host."""
        return LoadedConfig.featureFlags.hostname

    @staticmethod
    def get_feature_flag_port():
        """Obtain feature flag (Unleash) port."""
        return LoadedConfig.featureFlags.port

    @staticmethod
    def get_feature_flag_token():
        """Obtain feature flag (Unleash) token."""
        return LoadedConfig.featureFlags.clientAccessToken

    @staticmethod
    def get_in_memory_db_host():
        """Obtain in memory (redis) db host."""
        return LoadedConfig.inMemoryDb.hostname

    @staticmethod
    def get_in_memory_db_port():
        """Obtain in memory (redis) db port."""
        return LoadedConfig.inMemoryDb.port
        # return ENVIRONMENT.get_value("REDIS_PORT", default="6379")

    @staticmethod
    def get_kafka_broker_host():
        """Obtain kafka broker host address."""
        return LoadedConfig.kafka.brokers[0].hostname

    @staticmethod
    def get_kafka_broker_port():
        """Obtain kafka broker port."""
        return LoadedConfig.kafka.brokers[0].port

    @staticmethod
    def get_kafka_topic(requestedName: str):
        """Obtain kafka topic."""
        return KafkaTopics.get(requestedName).name

    @staticmethod
    def get_kafka_sasl():
        """Obtain kafka sasl"""
        return LoadedConfig.kafka.brokers[0].sasl

    @staticmethod
    def get_kafka_cacert():
        """Obtain kafka CA Certificate"""
        if LoadedConfig.kafka.brokers[0].cacert:
            return LoadedConfig.kafka_ca()
        return None

    @staticmethod
    def get_kafka_authtype():
        """Obtain kafka Authentication Type"""
        return LoadedConfig.kafka.brokers[0].authtype

    @staticmethod
    def get_cloudwatch_access_id():
        """Obtain cloudwatch access id."""
        return LoadedConfig.logging.cloudwatch.accessKeyId

    @staticmethod
    def get_cloudwatch_access_key():
        """Obtain cloudwatch access key."""
        return LoadedConfig.logging.cloudwatch.secretAccessKey

    @staticmethod
    def get_cloudwatch_region():
        """Obtain cloudwatch region."""
        return LoadedConfig.logging.cloudwatch.region

    @staticmethod
    def get_cloudwatch_log_group():
        """Obtain cloudwatch log group."""
        return LoadedConfig.logging.cloudwatch.logGroup

    @staticmethod
    def get_object_store_endpoint():
        """Obtain object store endpoint."""
        S3_SECURE = CONFIGURATOR.get_object_store_tls()
        S3_HOST = CONFIGURATOR.get_object_store_host()
        S3_PORT = CONFIGURATOR.get_object_store_port()

        S3_PREFIX = "https://" if S3_SECURE else "http://"
        endpoint = f"{S3_PREFIX}{S3_HOST}"
        if bool(S3_PORT):
            endpoint += f":{S3_PORT}"
        return endpoint

    @staticmethod
    def get_object_store_host():
        """Obtain object store host."""
        return LoadedConfig.objectStore.hostname

    @staticmethod
    def get_object_store_port():
        """Obtain object store port."""
        return LoadedConfig.objectStore.port

    @staticmethod
    def get_object_store_tls():
        """Obtain object store secret key."""
        value = LoadedConfig.objectStore.tls
        if type(value) == bool:
            return value
        if value and value.lower() in ["true", "false"]:
            return value.lower() == "true"
        else:
            return False

    @staticmethod
    def get_object_store_access_key(requestedName: str = ""):
        """Obtain object store access key."""
        if requestedName != "" and ObjectBuckets.get(requestedName):
            return ObjectBuckets.get(requestedName).accessKey
        if len(LoadedConfig.objectStore.buckets) > 0:
            return LoadedConfig.objectStore.buckets[0].accessKey
        if LoadedConfig.objectStore.accessKey:
            return LoadedConfig.objectStore.accessKey

    @staticmethod
    def get_object_store_secret_key(requestedName: str = ""):
        """Obtain object store secret key."""
        if requestedName != "" and ObjectBuckets.get(requestedName):
            return ObjectBuckets.get(requestedName).secretKey
        if len(LoadedConfig.objectStore.buckets) > 0:
            return LoadedConfig.objectStore.buckets[0].secretKey
        if LoadedConfig.objectStore.secretKey:
            return LoadedConfig.objectStore.secretKey

    @staticmethod
    def get_object_store_bucket(requestedName: str = ""):
        """Obtain object store bucket."""
        if ObjectBuckets.get(requestedName):
            return ObjectBuckets.get(requestedName).name
        return requestedName

    @staticmethod
    def get_object_store_region(requestedName: str = ""):
        """Obtain object store region."""
        if ObjectBuckets.get(requestedName):
            return ObjectBuckets.get(requestedName).region
        return None

    @staticmethod
    def get_database_name():
        """Obtain database name."""
        return LoadedConfig.database.name

    @staticmethod
    def get_database_user():
        """Obtain database user."""
        return LoadedConfig.database.username

    @staticmethod
    def get_database_password():
        """Obtain database password."""
        return LoadedConfig.database.password

    @staticmethod
    def get_database_host():
        """Obtain database host."""
        return LoadedConfig.database.hostname

    @staticmethod
    def get_database_port():
        """Obtain database port."""
        return LoadedConfig.database.port

    @staticmethod
    def get_database_ca():
        """Obtain database ca."""
        return LoadedConfig.database.rdsCa

    @staticmethod
    def get_database_ca_file():
        """Obtain database ca file."""
        if LoadedConfig.database.rdsCa:
            return LoadedConfig.rds_ca()
        return None

    @staticmethod
    def get_metrics_port():
        """Obtain metrics port."""
        return LoadedConfig.metricsPort

    @staticmethod
    def get_metrics_path():
        """Obtain metrics path."""
        return LoadedConfig.metricsPath

    @staticmethod
    def get_endpoint_host(app, name, default):
        """Obtain endpoint hostname."""
        endpoint = DependencyEndpoints.get(app, {}).get(name)
        if endpoint:
            return endpoint.hostname
        # if the endpoint is not defined by clowder, fall back to env variable
        svc = "_".join((app, name, "HOST")).replace("-", "_").upper()
        return ENVIRONMENT.get_value(svc, default=default)

    @staticmethod
    def get_endpoint_port(app, name, default):
        """Obtain endpoint port."""
        endpoint = DependencyEndpoints.get(app, {}).get(name)
        if endpoint:
            return endpoint.port
        # if the endpoint is not defined by clowder, fall back to env variable
        svc = "_".join((app, name, "PORT")).replace("-", "_").upper()
        return ENVIRONMENT.get_value(svc, default=default)


class ConfigFactory:
    """Returns configurator based on mode."""

    @staticmethod
    def get_configurator():
        """Returns configurator based on mode from env variable."""
        return ClowderConfigurator if CLOWDER_ENABLED else EnvConfigurator


CONFIGURATOR = ConfigFactory.get_configurator()
