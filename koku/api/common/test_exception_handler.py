#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the API exception handler module."""
from django.test import TestCase

from .exception_handler import _generate_errors_from_dict


class ExceptionHanlderTest(TestCase):
    """Tests against the exception handler functions."""

    def test_generate_errors_from_dict(self):
        """Test generating errors from dictionary errors."""
        kwargs = {"status_code": 400}
        response = {"non_field_errors": ["Cannot access AWS bucket with ARN", "ARN format is incorrect"]}
        formatted_errors = _generate_errors_from_dict(response, **kwargs)
        expected = [
            {"detail": "Cannot access AWS bucket with ARN", "source": "non_field_errors", "status": 400},
            {"detail": "ARN format is incorrect", "source": "non_field_errors", "status": 400},
        ]
        self.assertEqual(formatted_errors, expected)

        kwargs = {"status_code": 400}
        response = {"provider_type": "Must be either OCP or AWS"}
        formatted_errors = _generate_errors_from_dict(response, **kwargs)
        expected = [{"detail": "Must be either OCP or AWS", "source": "provider_type", "status": 400}]
        self.assertEqual(formatted_errors, expected)

        kwargs = {"status_code": 400}
        response = {"tiered_rate": {"unit": ['"UD" is not a valid choice.']}}
        formatted_errors = _generate_errors_from_dict(response, **kwargs)
        expected = [{"detail": '"UD" is not a valid choice.', "source": "tiered_rate.unit", "status": 400}]
        self.assertEqual(formatted_errors, expected)

        kwargs = {"status_code": 400}
        response = {"tiered_rate": {"value": ["Ensure that there are no more than 10 decimal places."]}}
        formatted_errors = _generate_errors_from_dict(response, **kwargs)
        expected = [
            {
                "detail": "Ensure that there are no more than 10 decimal places.",
                "source": "tiered_rate.value",
                "status": 400,
            }
        ]
        self.assertEqual(formatted_errors, expected)

        kwargs = {"status_code": 400}
        response = {"tiered_rate": {"value": {"key": "Ensure that there are no more than 10 decimal places."}}}
        formatted_errors = _generate_errors_from_dict(response, **kwargs)
        expected = [
            {
                "detail": "Ensure that there are no more than 10 decimal places.",
                "source": "tiered_rate.value.key",
                "status": 400,
            }
        ]
        self.assertEqual(formatted_errors, expected)

        kwargs = {"status_code": 400}
        response = {"tiered_rate": {"value": [["key"], ["Ensure that there are no more than 10 decimal places."]]}}
        formatted_errors = _generate_errors_from_dict(response, **kwargs)
        expected = [
            {"detail": "key", "source": "tiered_rate.value", "status": 400},
            {
                "detail": "Ensure that there are no more than 10 decimal places.",
                "source": "tiered_rate.value",
                "status": 400,
            },
        ]
        self.assertEqual(formatted_errors, expected)
