import json
import os
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

from api.common import RH_IDENTITY_HEADER
from api.iam.serializers import extract_header
from masu.external.kafka_msg_handler import process_messages


# header = """
# eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6IjEwMDAxIiwib3JnX2lkIjoiMTIzNDU2NyIsInR
# 5cGUiOiJVc2VyIiwidXNlciI6eyJ1c2VybmFtZSI6InVzZXJfZGV2IiwiZW1haWwiOiJ1c2VyX2Rldk
# Bmb28uY29tIiwiaXNfb3JnX2FkbWluIjp0cnVlLCJhY2Nlc3MiOnsgfX19LCJlbnRpdGxlbWVudHMiO
# nsiY29zdF9tYW5hZ2VtZW50Ijp7ImlzX2VudGl0bGVkIjp0cnVlfX19Cg==
# """


def get_s3_signature(url, file_name, method="get_object"):
    s3 = boto3.client(
        "s3",
        endpoint_url=url,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET,
        region_name=settings.S3_REGION,
    )
    return s3.generate_presigned_url(
        ClientMethod=method,
        Params={"Bucket": os.environ.get("S3_BUCKET_NAME_OCP_INGRESS"), "Key": file_name},
        ExpiresIn=86400,
    )


class MockMessage:
    """Test class for kafka msg."""

    def __init__(self, request, request_id, filename):
        """Initialize Msg."""
        s3_signature = get_s3_signature(settings.S3_ENDPOINT, filename)
        b64_identity, decoded_header = extract_header(request, RH_IDENTITY_HEADER)
        value_dict = {
            "url": s3_signature,
            "b64_identity": b64_identity,
            "request_id": request_id,
            "account": decoded_header.get("identity", {}).get("account_number"),
            "org_id": decoded_header.get("identity", {}).get("org_id"),
        }

        self._value = json.dumps(value_dict).encode("utf-8")

    def value(self):
        return self._value


def upload_file_to_s3(signature, data):
    return requests.put(signature, data=data)


def send_payload(request, request_id, filename):
    kmsg = MockMessage(request, request_id, filename)
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
    if request.method == "POST":
        for _, file in request.FILES.items():
            payload_name = file.name
            response_data["payload-name"].append(payload_name)
            s3_signature = get_s3_signature(settings.S3_ENDPOINT, payload_name, method="put_object")
            res = upload_file_to_s3(s3_signature, data=file.file)
            if res.status_code == 200:
                response_data["upload"] = "success"
            else:
                response_data["upload"] = "failed"
                response_data["failed-reason"] = res.reason
                return Response(response_data, status=res.status_code)
            send_payload(request, request_id, payload_name)
    else:
        params = request.query_params
        payload_names = params.get("payload_name", "")
        for payload_name in payload_names.split(","):
            send_payload(request, request_id, payload_name)
            response_data["payload-name"].append(payload_name)

    response_data["ingest-started"] = True

    return Response(response_data, status=202)
