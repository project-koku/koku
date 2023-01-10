# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from uuid import uuid4

from django.db import models


class HCSReport(models.Model):
    task_uuid = models.UUIDField(default=uuid4, primary_key=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    completed_timestamp = models.DateTimeField(null=True)
    report_location = models.CharField(max_length=256)
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE, null=True)

    def __str__(self):
        """Get the string representation."""
        return (
            f"Provider UUID: {self.provider}\n"
            f"AWS bucket location: {self.report_location}\n"
            f"Created time: {self.created_timestamp}\n"
            f"Processing completed: {self.completed_timestamp}\n"
            f"Processing task ID: {self.task_uuid}\n"
        )
