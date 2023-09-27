import json
import os
from threading import Thread
from uuid import uuid4

import boto3
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.external.kafka_msg_handler import process_messages


header = """
eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6IjEwMDAxIiwib3JnX2lkIjoiMTIzNDU2NyIsInR
5cGUiOiJVc2VyIiwidXNlciI6eyJ1c2VybmFtZSI6InVzZXJfZGV2IiwiZW1haWwiOiJ1c2VyX2Rldk
Bmb28uY29tIiwiaXNfb3JnX2FkbWluIjp0cnVlLCJhY2Nlc3MiOnsgfX19LCJlbnRpdGxlbWVudHMiO
nsiY29zdF9tYW5hZ2VtZW50Ijp7ImlzX2VudGl0bGVkIjp0cnVlfX19Cg==
"""


def get_s3_signature(url, file_name):
    s3 = boto3.client(
        "s3",
        endpoint_url=url,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET,
        region_name=settings.S3_REGION,
    )
    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": os.environ.get("S3_BUCKET_NAME_OCP_INGRESS"), "Key": file_name},
        ExpiresIn=86400,
    )


class MockMessage:
    """Test class for kafka msg."""

    def __init__(
        self,
        request_id,
        filename,
        b64_identity=header,
    ):
        """Initialize Msg."""
        s3_signature = get_s3_signature(settings.S3_ENDPOINT, filename)
        value_dict = {
            "url": s3_signature,
            "b64_identity": b64_identity,
            "request_id": request_id,
            "account": "10001",
            "org_id": "1234567",
        }

        self._value = json.dumps(value_dict).encode("utf-8")

    def value(self):
        return self._value


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def ingest_ocp_payload(request):
    """Return download file async task ID."""
    request_id = uuid4().hex
    params = request.query_params
    payload_name = params.get("payload_name")
    kmsg = MockMessage(request_id, filename=payload_name)
    # async_task_id = process_messages.delay(kmsg)

    # return Response({"Download Request Task ID": str(async_task_id)})

    t = Thread(target=process_messages, args=(kmsg,))
    t.start()

    return Response({"ocp ingress started in thread, request id": str(request_id)})
