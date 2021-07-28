# API views for manifests
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import viewsets

from masu.api.manifest.serializers import ManifestSerializer
from reporting_common.models import CostUsageReportManifest


class ManifestView(viewsets.ModelViewSet):
    queryset = CostUsageReportManifest.objects.all()
    serializer_class = ManifestSerializer
    ordering_fields = (
        "assembly_id",
        "manifest_creation_Datetime",
        "manifest_updated_datetime",
        "manifest_completed_datetime",
        "manifest_modified_datetime",
        "billing_period_start_datetime",
        "num_total_files",
        "provider_id",
        "s3_csv_cleared",
        "s3_parquet_cleared",
        "operator_version",
    )
    ordering = ("provider_id",)
    http_method_names = ["get", "post", "head", "delete", "put"]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        response = super().list(self, request=request, args=args, kwargs=kwargs)

        return response
