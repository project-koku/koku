#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import rest_framework.test
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase
from api.settings.platform.view import PlatformCategoriesView


class TestPlatformProjectsAPI(IamTestCase):
    @property
    def url(self):
        return reverse("settings-platform")

    @property
    def default_projects(self):
        return sorted(PlatformCategoriesView._default_platform_projects)

    def test_get(self):
        """Get the current platform projects"""

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.get(self.url, **self.headers)

        result = sorted(response.data["data"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(result, self.default_projects)

    def test_update_platforms(self):
        """Add more projects to the platform projects"""

        body = {
            "projects": [
                "New",
                "Project",
            ]
        }
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.put(self.url, body, format="json", **self.headers)

        projects = response.data.get("data", [])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(set(body["projects"]).issubset(projects))

    def test_delete_default_platforms(self):
        """Ensure default platform categories cannot be deleted"""

        body = {"projects": self.default_projects}
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.delete(self.url, body, format="json", **self.headers)

        projects = sorted(response.data.get("data", []))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(projects, self.default_projects)

    def test_delete_platforms(self):
        """Test deleting platform projects"""

        additional_projects = [
            "New-Project-%",
            "Overhead",
            "More-Overhead-%",
        ]

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()

            # Get current list of platform projects
            initial_response = client.get(self.url, **self.headers)
            initial_projects = sorted(initial_response.data.get("data", []))

            # Add platform projects
            put_response = client.put(self.url, {"projects": additional_projects}, **self.headers)
            updated_projects = sorted(put_response.data.get("data", []))

            # Delete one non-default platform project
            delete_response = client.delete(self.url, {"projects": additional_projects[0]}, **self.headers)
            final_projects = sorted(delete_response.data.get("data", []))

        # The final platform projects should be the default projects plus those that were add but not deleted
        expected_final_projects = sorted(additional_projects[1:] + self.default_projects)

        self.assertFalse(set(additional_projects).issubset(initial_projects))
        self.assertTrue(set(additional_projects).issubset(updated_projects))
        self.assertEqual(expected_final_projects, final_projects)

    def test_put_invalid(self):
        """Ensure invalid PUT requests return a 400 status"""

        test_cases = (
            ({"projects": []}, "may not be empty"),
            ({"projects": [True]}, "not a valid string"),
            ({"nope": []}, "field is required"),
        )
        for case, expected in test_cases:
            with schema_context(self.schema_name):
                client = rest_framework.test.APIClient()
                response = client.put(self.url, case, format="json", **self.headers)

            error = response.data.get("errors", [{}])[0].get("detail")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(expected, error.lower())

    def test_delete_invalid(self):
        """Ensure invalid DELETE requests return a 400 status"""
        test_cases = (
            ({"projects": []}, "may not be empty"),
            ({"projects": [True]}, "not a valid string"),
            ({"nope": []}, "field is required"),
        )
        for case, expected in test_cases:
            with schema_context(self.schema_name):
                client = rest_framework.test.APIClient()
                response = client.delete(self.url, case, format="json", **self.headers)

            error = response.data.get("errors", [{}])[0].get("detail")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(expected, error.lower())
