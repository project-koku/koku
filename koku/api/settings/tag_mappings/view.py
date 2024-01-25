from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .query_handler import format_tag_mapping_relationship
from .serializers import TagMappingSerializer
from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from reporting.provider.all.models import TagMapping, EnabledTagKeys


class SettingsTagMappingView(generics.GenericAPIView):
    queryset = TagMapping.objects.all()
    serializer_class = TagMappingSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)
        paginator = ListPaginator(serializer.data, request)
        response = paginator.paginated_response
        response = format_tag_mapping_relationship(response)

        return response


class SettingsTagMappingChildAddView(APIView):
    permission_classes = (SettingsAccessPermission,)
    serializer_class = TagMappingSerializer

    @transaction.atomic
    def put(self, request):
        try:
            parent_uuid = request.data.get("parent")
            children_uuids = request.data.get("children", [])

            parent = EnabledTagKeys.objects.get(uuid=parent_uuid)
            children = EnabledTagKeys.objects.filter(uuid__in=children_uuids)

            if not parent or not children.exists():
                return Response({"detail": "Invalid parent or children UUIDs."}, status=status.HTTP_400_BAD_REQUEST)

            # Validate if parent can be a child in any existing mappings
            if TagMapping.objects.filter(child=parent_uuid).exists():
                return Response({"detail": "A child can't become a parent."}, status=status.HTTP_400_BAD_REQUEST)

            # Validate if children can be parents in any existing mappings
            if TagMapping.objects.filter(parent__in=children_uuids).exists():
                return Response({"detail": "A parent can't become a child."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                # Create TagMapping for each child
                for child in children:
                    TagMapping.objects.create(parent=parent, child=child)

            # Serialize and return the created TagMapping
            serializer = TagMappingSerializer(TagMapping.objects.filter(parent=parent), many=True)
            
            return Response(serializer.data, status=status.HTTP_200_OK)

        except EnabledTagKeys.DoesNotExist:
            return Response({"detail": "Invalid parent or children UUIDs."}, status=status.HTTP_400_BAD_REQUEST)
