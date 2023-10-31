from http import HTTPStatus
from unittest.mock import MagicMock
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from masu.api.ingest_ocp_payload import ingest_ocp_payload


class QueryParametersTests(TestCase):
    def test_ingest_ocp_payload(self):
        # Arrange
        file1 = SimpleUploadedFile("file1.gz", b"file_content", content_type="multipart/form-data")
        file2 = SimpleUploadedFile("file2.gz", b"file_content", content_type="multipart/form-data")
        test_table = [
            # Happy path tests
            (
                "POST",
                {"file1": file1, "file2": file2},
                "",
                HTTPStatus.ACCEPTED,
                {"upload": "success"},
                "happy_path_post",
            ),
            ("GET", {}, "?payload_name=file1,file2", HTTPStatus.ACCEPTED, {}, "happy_path_get"),
            # Edge cases
            ("POST", {}, "", HTTPStatus.ACCEPTED, {}, "edge_case_no_files_post"),
            ("GET", {}, "", HTTPStatus.ACCEPTED, {}, "edge_case_no_payload_name_get"),
            # Error cases
            ("POST", {"file1": file1}, "", HTTPStatus.INTERNAL_SERVER_ERROR, {"upload": "failed"}, "error_case_post"),
            ("GET", {}, "?payload_name=non_existent_file", HTTPStatus.ACCEPTED, {}, "error_case_get"),
        ]
        for test in test_table:
            method, files, query_params, expected_status, expected_response, test_id = test
            with self.subTest(test=test_id):

                mock_response = MagicMock()
                mock_response.status_code = (
                    HTTPStatus.OK if expected_response.get("upload") != "failed" else HTTPStatus.INTERNAL_SERVER_ERROR
                )
                mock_response.reason = "Some reason"

                with patch("masu.api.ingest_ocp_payload.get_s3_signature") as mock_get_s3_signature, patch(
                    "masu.api.ingest_ocp_payload.upload_file_to_s3", return_value=mock_response
                ) as mock_upload_file_to_s3, patch("masu.api.ingest_ocp_payload.send_payload") as mock_send_payload:

                    request = (
                        APIRequestFactory().get(f"/{query_params}")
                        if method == "GET"
                        else APIRequestFactory().post("/", data=files)
                    )

                    # Act
                    response = ingest_ocp_payload(request)

                    # Assert
                    self.assertEqual(response.status_code, expected_status)
                    if method == "POST" and files:
                        mock_get_s3_signature.assert_called()
                        mock_upload_file_to_s3.assert_called()
                    if method == "GET" and "payload_name" in query_params:
                        mock_send_payload.assert_called()
                    if expected_response.get("upload") != "failed":
                        self.assertTrue(response.data["ingest-started"])
                    for key, value in expected_response.items():
                        self.assertEqual(response.data[key], value)
