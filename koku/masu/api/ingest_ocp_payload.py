#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""
Masu API for POSTing and ingesting OCP payloads.

POSTed payloads are uploaded to S3 and ingested. Multiple files may be posted simulataneously.
The org_id query parameter is required for all requests:

```
$ curl -F 'file2=@path/to/payload/payload-name-2.gz'  \
    -F 'file1=@path/to/payload/payload-name-1.gz'  \
    'http://localhost:5042/api/cost-management/v1/ingest_ocp_payload/?org_id=1234567'
```

Files already in the bucket in S3 can be ingested via a GET request. Multiple files can
be ingested simultaneously by providing a comma separated list of payload names:

```
http://localhost:5042/api/cost-management/v1/ingest_ocp_payload/?org_id=1234567&payload_name=payload-name-1.gz,payload-name-2.gz
```
"""
import json
from http import HTTPStatus
from threading import Thread
from uuid import uuid4

import boto3
import requests
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from koku.env import ENVIRONMENT
from masu.external.kafka_msg_handler import process_messages


OCP_INGRESS_BUCKET = ENVIRONMENT.get_value("S3_BUCKET_NAME_OCP_INGRESS", default="ocp-ingress")


class MockMessage:
    """Test class for kafka msg."""

    def __init__(self, request_id, filename, org_id):
        """Initialize MockMessage."""
        s3_signature = get_s3_signature(settings.S3_ENDPOINT, filename)
        value_dict = {"url": s3_signature, "b64_identity": "", "request_id": request_id, "org_id": org_id}

        self._value = json.dumps(value_dict).encode("utf-8")

    def value(self):
        return self._value


def get_s3_signature(url, file_name, *, bucket=OCP_INGRESS_BUCKET, method="get_object"):  # pragma: no cover
    """Generate an s3 signature for a file in S3."""
    s3 = boto3.client(
        "s3",
        endpoint_url=url,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET,
        region_name=settings.S3_REGION,
    )
    return s3.generate_presigned_url(
        ClientMethod=method,
        Params={"Bucket": bucket, "Key": file_name},
        ExpiresIn=86400,
    )


def upload_file_to_s3(signature, data):  # pragma: no cover
    """Upload file to s3."""
    return requests.put(signature, data=data)


def send_payload(request_id, filename, org_id):  # pragma: no cover
    """Create the mock Kafka message and start ingestion in a thread."""
    kmsg = MockMessage(request_id, filename, org_id)
    t = Thread(target=process_messages, args=(kmsg,))
    t.start()


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def ingest_ocp_payload(request):
    """Return download file async task ID."""
    request_id = uuid4().hex
    response_data = {"request-id": request_id, "payload-name": []}

    # org_id is required for local OCP ingestion
    params = request.query_params
    org_id = params.get("org_id")
    if not org_id:
        response_data["error"] = "org_id is required"
        return Response(response_data, status=HTTPStatus.BAD_REQUEST)

    if request.method == "POST":
        if not request.FILES:
            response_data["error"] = "no payload sent"
            return Response(response_data, status=HTTPStatus.BAD_REQUEST)
        for _, file in request.FILES.items():
            payload_name = file.name
            response_data["payload-name"].append(payload_name)
            s3_signature = get_s3_signature(settings.S3_ENDPOINT, payload_name, method="put_object")
            res = upload_file_to_s3(s3_signature, data=file.file)
            if res.status_code == HTTPStatus.OK:
                response_data["upload"] = "success"
            else:
                response_data["upload"] = "failed"
                response_data["failed-reason"] = res.reason
                return Response(response_data, status=res.status_code)
            send_payload(request_id, payload_name, org_id)
    else:
        payload_names = params.get("payload_name")
        if not payload_names:
            response_data["error"] = "no payload sent"
            return Response(response_data, status=HTTPStatus.BAD_REQUEST)
        for payload_name in payload_names.split(","):
            send_payload(request_id, payload_name, org_id)
            response_data["payload-name"].append(payload_name)

    response_data["ingest-started"] = True

    return Response(response_data, status=HTTPStatus.ACCEPTED)
